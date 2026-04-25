"""
PR Agent - Applies safe auto-fixes and opens a remediation pull request.

Design goals:
- Reuse existing analyzer outputs (security findings) for efficiency.
- Apply only conservative, deterministic fixes for known patterns.
- Validate via git diff + commit flow and open PR through GitHub service.
"""
import ast
import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.mcp_github_service import MCPGitHubService
from app.services.llm_service import LLMService


class PRAgent:
    """Autonomous remediation and pull-request agent."""

    def __init__(
        self,
        github_service: Optional[MCPGitHubService] = None,
        llm_service: Optional[LLMService] = None,
    ):
        self.github_service = github_service or MCPGitHubService()
        self.llm_service = llm_service or LLMService()
        self.default_mode = os.getenv("REMEDIATION_MODE", "deterministic").strip().lower()
        self.max_attempts = int(os.getenv("REMEDIATION_MAX_ATTEMPTS", "2"))
        self.max_files = int(os.getenv("REMEDIATION_MAX_FILES", "3"))
        self.post_pr_review_enabled = os.getenv("POST_PR_REVIEW_ENABLED", "true").lower() in (
            "1", "true", "yes", "on"
        )

    def _effective_mode(self, remediation_mode: Optional[str]) -> str:
        mode = (remediation_mode or self.default_mode or "deterministic").strip().lower()
        if mode not in ("deterministic", "nondeterministic"):
            return "deterministic"
        return mode

    def _run_git(self, repo_path: str, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _extract_code_block_or_text(self, content: str) -> str:
        """Extract first fenced block if present, else return raw content."""
        if not content:
            return ""
        match = re.search(r"```(?:\w+)?\n(.*?)```", content, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip()

    def _resolve_issue_file_path(self, repo_path: str, issue: Dict[str, Any]) -> Optional[str]:
        raw_path = issue.get("file")
        if not raw_path or not isinstance(raw_path, str):
            return None
        if os.path.isabs(raw_path) and os.path.exists(raw_path):
            return raw_path

        normalized = raw_path.lstrip("./")
        candidates = [os.path.join(repo_path, normalized)]

        # SpotBugs often returns package-relative paths for Java source files.
        if issue.get("language") == "java":
            candidates.append(os.path.join(repo_path, "src/main/java", normalized))

        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _collect_nondeterministic_issues_by_file(
        self, repo_path: str, scan_result: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        raw_results = scan_result.get("raw_results", {})
        allowed_ext = {".py", ".java", ".js", ".jsx", ".ts", ".tsx"}
        by_file: Dict[str, List[Dict[str, Any]]] = {}

        for analyzer_name in ("security", "oss", "deprecation"):
            for issue in raw_results.get(analyzer_name, []):
                file_path = self._resolve_issue_file_path(repo_path, issue)
                if not file_path:
                    continue
                if os.path.splitext(file_path)[1].lower() not in allowed_ext:
                    continue

                if file_path not in by_file and len(by_file) >= self.max_files:
                    continue
                by_file.setdefault(file_path, []).append({"analyzer": analyzer_name, **issue})
        return by_file

    def _validate_candidate_change(
        self, repo_path: str, file_path: str, candidate: str
    ) -> Tuple[bool, str]:
        if not candidate.strip():
            return False, "empty_candidate"

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".py":
                ast.parse(candidate)
            elif ext == ".java":
                if candidate.count("{") != candidate.count("}"):
                    return False, "java_brace_mismatch"
        except Exception as e:
            return False, f"syntax_validation_failed: {e}"

        rel = os.path.relpath(file_path, repo_path)
        diff = self._run_git(repo_path, ["diff", "--", rel])
        if diff.returncode != 0:
            return False, f"git_diff_failed: {diff.stderr}"
        if not diff.stdout.strip():
            return False, "no_effective_diff"
        return True, "validated"

    def _generate_nondeterministic_candidate(
        self,
        file_path: str,
        original_content: str,
        issues: List[Dict[str, Any]],
        attempt: int,
    ) -> str:
        compact_issues = issues[:5]
        prompt = f"""You are fixing code issues in a single file.

File path: {file_path}
Attempt: {attempt}

Issues to fix (JSON):
{json.dumps(compact_issues, indent=2, default=str)}

Current file content:
```text
{original_content}
```

Return ONLY the complete updated file content.
Do not include markdown, explanations, or code fences.
Preserve unrelated logic.
"""
        response = self.llm_service.generate(
            prompt=prompt,
            system_prompt=(
                "You are a senior software engineer. "
                "Return only valid source code for the full file content."
            ),
            temperature=0.2,
            max_tokens=2048,
        )
        return self._extract_code_block_or_text(response)

    def _apply_nondeterministic_fixes(
        self, repo_path: str, scan_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.llm_service.is_available():
            return {
                "changed_files": [],
                "details": [],
                "reason": "llm_unavailable",
            }

        by_file = self._collect_nondeterministic_issues_by_file(repo_path, scan_result)
        if not by_file:
            return {
                "changed_files": [],
                "details": [],
                "reason": "no_file_scoped_issues",
            }

        changed_files: List[str] = []
        details: List[Dict[str, Any]] = []

        for file_path, issues in by_file.items():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original = f.read()
            except Exception as e:
                details.append(
                    {
                        "file": os.path.relpath(file_path, repo_path),
                        "status": "failed",
                        "reason": f"read_failed: {e}",
                    }
                )
                continue

            applied = False
            last_reason = "no_candidate"
            for attempt in range(1, max(1, self.max_attempts) + 1):
                try:
                    candidate = self._generate_nondeterministic_candidate(
                        file_path=file_path,
                        original_content=original,
                        issues=issues,
                        attempt=attempt,
                    )
                except Exception as e:
                    last_reason = f"generation_failed: {e}"
                    continue

                if not candidate or candidate.strip() == original.strip():
                    last_reason = "unchanged_candidate"
                    continue

                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(candidate)
                except Exception as e:
                    last_reason = f"write_failed: {e}"
                    continue

                valid, reason = self._validate_candidate_change(repo_path, file_path, candidate)
                if valid:
                    changed_files.append(file_path)
                    details.append(
                        {
                            "file": os.path.relpath(file_path, repo_path),
                            "status": "applied",
                            "attempt": attempt,
                            "issues_considered": len(issues),
                        }
                    )
                    applied = True
                    break

                # Restore original on failed validation attempt.
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(original)
                last_reason = reason

            if not applied:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(original)
                details.append(
                    {
                        "file": os.path.relpath(file_path, repo_path),
                        "status": "failed",
                        "reason": last_reason,
                        "issues_considered": len(issues),
                    }
                )

        return {
            "changed_files": changed_files,
            "details": details,
            "reason": None if changed_files else "no_valid_ai_fixes",
        }

    def _commit_push_and_create_pr(
        self,
        repo_path: str,
        owner: str,
        repo: str,
        changed_files: List[str],
        base_branch: str,
        branch_name: str,
        commit_msg: str,
        title: str,
        body: str,
        mode: str,
        scan_result: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        checkout = self._run_git(repo_path, ["checkout", "-b", branch_name])
        if checkout.returncode != 0:
            return {"created": False, "reason": f"git_checkout_failed: {checkout.stderr}", "mode": mode}

        rel_changed = [os.path.relpath(f, repo_path) for f in changed_files]
        add = self._run_git(repo_path, ["add"] + rel_changed)
        if add.returncode != 0:
            return {"created": False, "reason": f"git_add_failed: {add.stderr}", "mode": mode}

        commit = self._run_git(repo_path, ["commit", "-m", commit_msg])
        if commit.returncode != 0:
            return {
                "created": False,
                "reason": f"git_commit_failed: {commit.stderr or commit.stdout}",
                "mode": mode,
            }

        push = self._run_git(repo_path, ["push", "-u", "origin", branch_name])
        if push.returncode != 0:
            return {"created": False, "reason": f"git_push_failed: {push.stderr or push.stdout}", "mode": mode}

        try:
            pr = self.github_service.create_pull_request(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                head=branch_name,
                base=base_branch,
            )
            payload = {
                "created": True,
                "mode": mode,
                "branch": branch_name,
                "changed_files": rel_changed,
                "pull_request": pr,
            }
            review = self._post_pr_review(
                owner=owner,
                repo=repo,
                pull_number=pr["number"],
                repo_path=repo_path,
                changed_files=rel_changed,
                scan_result=scan_result or {},
                mode=mode,
            )
            payload["post_pr_review"] = review
            if extra:
                payload.update(extra)
            return payload
        except Exception as e:
            payload = {
                "created": False,
                "reason": f"create_pr_failed: {e}",
                "mode": mode,
                "branch": branch_name,
                "changed_files": rel_changed,
            }
            if extra:
                payload.update(extra)
            return payload

    def _collect_changed_file_snippets(
        self, repo_path: str, changed_files: List[str], max_files: int = 5, max_chars: int = 1200
    ) -> Dict[str, str]:
        snippets: Dict[str, str] = {}
        for rel_path in changed_files[:max_files]:
            abs_path = os.path.join(repo_path, rel_path)
            if not os.path.exists(abs_path):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                snippets[rel_path] = content[:max_chars]
            except Exception:
                continue
        return snippets

    def _build_review_body(
        self,
        repo_path: str,
        changed_files: List[str],
        scan_result: Dict[str, Any],
        mode: str,
    ) -> str:
        summary = (scan_result.get("report") or {}).get("summary", {})
        if not self.llm_service.is_available():
            return (
                "## Automated Post-PR Review\n\n"
                f"- Remediation mode: `{mode}`\n"
                f"- Changed files: {len(changed_files)}\n"
                f"- Total findings in scan report: {summary.get('total_issues', 'n/a')}\n\n"
                "Please verify:\n"
                "- unit/integration tests\n"
                "- edge cases and null handling\n"
                "- dependency and security checks\n"
            )

        snippets = self._collect_changed_file_snippets(repo_path, changed_files)
        prompt = f"""Review this remediation PR and provide concise review comments.

Remediation mode: {mode}
Changed files: {changed_files}
Scan summary: {json.dumps(summary, default=str)}

Updated file snippets (truncated):
{json.dumps(snippets, indent=2, default=str)}

Return markdown with:
1) Overall risk (Low/Medium/High)
2) 3-6 actionable review comments
3) Required follow-up validation checks
Keep it concise and practical.
"""
        return self.llm_service.generate(
            prompt=prompt,
            system_prompt="You are a senior code reviewer focused on correctness and security.",
            temperature=0.2,
            max_tokens=900,
        ).strip()

    def _post_pr_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        repo_path: str,
        changed_files: List[str],
        scan_result: Dict[str, Any],
        mode: str,
    ) -> Dict[str, Any]:
        if not self.post_pr_review_enabled:
            return {"created": False, "reason": "post_pr_review_disabled"}
        try:
            body = self._build_review_body(
                repo_path=repo_path,
                changed_files=changed_files,
                scan_result=scan_result,
                mode=mode,
            )
        except Exception as e:
            body = (
                "## Automated Post-PR Review\n\n"
                f"Review generation failed: {e}\n"
                "- Please run tests and static analysis before merge."
            )
        try:
            review = self.github_service.create_pull_request_review(
                owner=owner,
                repo=repo,
                pull_number=pull_number,
                body=body,
                event="COMMENT",
            )
            return {
                "created": True,
                "review": review,
            }
        except Exception as e:
            return {
                "created": False,
                "reason": f"create_review_failed: {e}",
            }

    def _ensure_import(self, content: str, import_line: str) -> str:
        if import_line in content:
            return content
        package_match = re.search(r"^package\s+[^\n;]+;\s*$", content, flags=re.MULTILINE)
        if package_match:
            insert_at = package_match.end()
            return content[:insert_at] + f"\n\nimport {import_line};" + content[insert_at:]
        return f"import {import_line};\n{content}"

    def _apply_collection_defensive_copies(self, content: str) -> str:
        """
        Apply conservative defensive-copy fixes for mutable collection getters/setters.
        Handles List/Set/Map signatures in explicit methods.
        """
        original = content

        # Getter: return field; -> return field == null ? null : new X<>(field);
        getter_pattern = re.compile(
            r"(public\s+)(List<[^>]+>|Set<[^>]+>|Map<[^>]+,\s*[^>]+>)\s+"
            r"(\w+)\s*\(\s*\)\s*\{\s*return\s+(?:this\.)?(\w+)\s*;\s*\}",
            flags=re.DOTALL,
        )

        def _getter_repl(m: re.Match) -> str:
            type_sig = m.group(2)
            field = m.group(4)
            if type_sig.startswith("List<"):
                return (
                    f"{m.group(1)}{type_sig} {m.group(3)}() "
                    f"{{ return {field} == null ? null : new ArrayList<>({field}); }}"
                )
            if type_sig.startswith("Set<"):
                return (
                    f"{m.group(1)}{type_sig} {m.group(3)}() "
                    f"{{ return {field} == null ? null : new HashSet<>({field}); }}"
                )
            if type_sig.startswith("Map<"):
                return (
                    f"{m.group(1)}{type_sig} {m.group(3)}() "
                    f"{{ return {field} == null ? null : new HashMap<>({field}); }}"
                )
            return m.group(0)

        content = getter_pattern.sub(_getter_repl, content)

        # Setter: this.field = param; -> this.field = param == null ? null : new X<>(param);
        setter_pattern = re.compile(
            r"(public\s+void\s+set\w+\s*\(\s*)"
            r"(List<[^>]+>|Set<[^>]+>|Map<[^>]+,\s*[^>]+>)\s+(\w+)\s*"
            r"(\)\s*\{\s*this\.(\w+)\s*=\s*)(\w+)(\s*;\s*\})",
            flags=re.DOTALL,
        )

        def _setter_repl(m: re.Match) -> str:
            type_sig = m.group(2)
            param = m.group(3)
            field = m.group(5)
            rhs = m.group(6)
            if param != rhs:
                return m.group(0)
            if type_sig.startswith("List<"):
                assign = f"{field} = {param} == null ? null : new ArrayList<>({param})"
            elif type_sig.startswith("Set<"):
                assign = f"{field} = {param} == null ? null : new HashSet<>({param})"
            elif type_sig.startswith("Map<"):
                assign = f"{field} = {param} == null ? null : new HashMap<>({param})"
            else:
                return m.group(0)
            return f"{m.group(1)}{type_sig} {param}{m.group(4)}this.{assign}{m.group(7)}"

        content = setter_pattern.sub(_setter_repl, content)

        if content != original:
            if "new ArrayList<" in content:
                content = self._ensure_import(content, "java.util.ArrayList")
            if "new HashSet<" in content:
                content = self._ensure_import(content, "java.util.HashSet")
            if "new HashMap<" in content:
                content = self._ensure_import(content, "java.util.HashMap")
        return content

    def _apply_equals_hashcode_fix(self, content: str) -> str:
        """
        Add hashCode() if equals() exists and hashCode() is missing.
        Uses fields observed in equals() comparisons when possible.
        """
        if " boolean equals(" not in content and " boolean equals (" not in content:
            return content
        if " int hashCode(" in content or " int hashCode (" in content:
            return content

        fields: Set[str] = set()
        for m in re.finditer(r"Objects\.equals\((?:this\.)?(\w+),\s*(?:that\.)?\1\)", content):
            fields.add(m.group(1))
        for m in re.finditer(r"(?:this\.)?(\w+)\s*==\s*that\.\1", content):
            fields.add(m.group(1))

        field_expr = ", ".join(sorted(fields)) if fields else "getClass()"
        hashcode_method = (
            "\n    @Override\n"
            "    public int hashCode() {\n"
            f"        return Objects.hash({field_expr});\n"
            "    }\n"
        )

        # Append before last class closing brace.
        idx = content.rfind("}")
        if idx == -1:
            return content
        updated = content[:idx] + hashcode_method + content[idx:]
        return self._ensure_import(updated, "java.util.Objects")

    def _apply_java_fixes(self, file_path: str, issues: List[Dict[str, Any]]) -> bool:
        if not os.path.exists(file_path):
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception:
            return False

        content = original
        bug_types = {(i.get("bug_type") or "").upper() for i in issues}

        if "EI_EXPOSE_REP" in bug_types or "EI_EXPOSE_REP2" in bug_types:
            content = self._apply_collection_defensive_copies(content)
        if "HE_EQUALS_USE_HASHCODE" in bug_types:
            content = self._apply_equals_hashcode_fix(content)

        if content == original:
            return False
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    def _collect_fixable_security_issues(
        self, repo_path: str, scan_result: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns file_path -> issues for fixable Java SpotBugs patterns.
        """
        raw_results = scan_result.get("raw_results", {})
        security_issues = raw_results.get("security", [])
        fixable_bug_types = {"EI_EXPOSE_REP", "EI_EXPOSE_REP2", "HE_EQUALS_USE_HASHCODE"}
        by_file: Dict[str, List[Dict[str, Any]]] = {}
        for issue in security_issues:
            if issue.get("language") != "java":
                continue
            if issue.get("tool") != "spotbugs":
                continue
            bug_type = (issue.get("bug_type") or "").upper()
            if bug_type not in fixable_bug_types:
                continue
            rel_file = issue.get("file")
            if not rel_file:
                continue
            abs_file = os.path.join(repo_path, "src/main/java", rel_file)
            by_file.setdefault(abs_file, []).append(issue)
        return by_file

    def _collect_fixable_security_issues_from_list(
        self, repo_path: str, security_issues: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Returns file_path -> issues for fixable Java SpotBugs patterns."""
        fixable_bug_types = {"EI_EXPOSE_REP", "EI_EXPOSE_REP2", "HE_EQUALS_USE_HASHCODE"}
        by_file: Dict[str, List[Dict[str, Any]]] = {}
        for issue in security_issues:
            if issue.get("language") != "java":
                continue
            if issue.get("tool") != "spotbugs":
                continue
            bug_type = (issue.get("bug_type") or "").upper()
            if bug_type not in fixable_bug_types:
                continue
            rel_file = issue.get("file")
            if not rel_file:
                continue
            abs_file = os.path.join(repo_path, "src/main/java", rel_file)
            by_file.setdefault(abs_file, []).append(issue)
        return by_file

    def engage_after_analyzer(
        self,
        repo_path: str,
        analyzer_name: str,
        analyzer_issues: List[Dict[str, Any]],
        remediation_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Lightweight post-analyzer engagement hook.

        This runs after each analyzer execution so the remediation layer can
        react immediately. For now:
        - security: reports deterministic fixability summary
        - oss/deprecation: reports issue summary + current remediation mode
        """
        analyzer_name = (analyzer_name or "").lower()
        mode = self._effective_mode(remediation_mode)
        issue_count = len(analyzer_issues or [])

        if analyzer_name == "security":
            by_file = self._collect_fixable_security_issues_from_list(
                repo_path, analyzer_issues or []
            )
            fixable_count = sum(len(v) for v in by_file.values())
            return {
                "analyzer": "security",
                "engaged": True,
                "issues_seen": issue_count,
                "fixable_issues": fixable_count,
                "fixable_files": [os.path.relpath(p, repo_path) for p in by_file.keys()],
                "mode": mode,
            }

        if analyzer_name == "oss":
            vulnerable_pkgs = 0
            for issue in analyzer_issues or []:
                vulns = issue.get("vulnerabilities") or []
                if isinstance(vulns, list) and len(vulns) > 0:
                    vulnerable_pkgs += 1
            return {
                "analyzer": "oss",
                "engaged": True,
                "issues_seen": issue_count,
                "vulnerable_packages": vulnerable_pkgs,
                "mode": mode,
                "note": (
                    "Auto code changes for OSS are disabled in deterministic mode; "
                    "use upgrade policy + lockfile PR flow."
                    if mode == "deterministic"
                    else "Non-deterministic mode enabled; dependency upgrade planning can be LLM-driven."
                ),
            }

        if analyzer_name == "deprecation":
            files = sorted(
                {
                    os.path.relpath(i.get("file"), repo_path)
                    for i in (analyzer_issues or [])
                    if i.get("file")
                }
            )
            return {
                "analyzer": "deprecation",
                "engaged": True,
                "issues_seen": issue_count,
                "files": files[:50],
                "mode": mode,
                "note": (
                    "Deprecation remediations typically need semantic code transforms and tests."
                    if mode == "deterministic"
                    else "Non-deterministic mode enabled; semantic transforms can be proposed with validation."
                ),
            }

        return {
            "analyzer": analyzer_name,
            "engaged": True,
            "issues_seen": issue_count,
            "mode": "unsupported",
        }

    def create_fix_pr(
        self,
        repo_path: str,
        owner: str,
        repo: str,
        scan_result: Dict[str, Any],
        base_branch: str = "main",
        title_prefix: str = "fix",
        remediation_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply safe fixes and create a PR.
        """
        mode = self._effective_mode(remediation_mode)
        if not self.github_service.is_available():
            return {"created": False, "reason": "github_unavailable", "mode": mode}

        if mode == "nondeterministic":
            ai_fix_result = self._apply_nondeterministic_fixes(
                repo_path=repo_path,
                scan_result=scan_result,
            )
            changed_files = ai_fix_result.get("changed_files", [])
            if not changed_files:
                return {
                    "created": False,
                    "reason": ai_fix_result.get("reason", "no_valid_ai_fixes"),
                    "mode": mode,
                    "details": ai_fix_result.get("details", []),
                }

            branch_name = f"cip/{title_prefix}-ai-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
            commit_msg = (
                "fix: apply AI-assisted remediations from analyzer findings\n\n"
                "- generate candidate patches per file\n"
                "- validate syntax/structure before commit\n"
            )
            title = "fix: AI-assisted remediation for analyzer findings"
            body_lines = [
                "## AI-assisted remediation PR",
                "",
                "This PR was generated using non-deterministic remediation mode.",
                "",
                "### Validation gates",
                "- Candidate generated by LLM per file",
                "- Syntax/structure validation per language",
                "- Git diff required before acceptance",
                "",
                "### Files changed",
            ]
            for f in changed_files:
                body_lines.append(f"- `{os.path.relpath(f, repo_path)}`")
            body_lines.append("")
            body_lines.append("### Notes")
            body_lines.append("- Please run full project tests before merging.")
            body = "\n".join(body_lines)
            return self._commit_push_and_create_pr(
                repo_path=repo_path,
                owner=owner,
                repo=repo,
                changed_files=changed_files,
                base_branch=base_branch,
                branch_name=branch_name,
                commit_msg=commit_msg,
                title=title,
                body=body,
                mode=mode,
                scan_result=scan_result,
                extra={"details": ai_fix_result.get("details", [])},
            )

        by_file = self._collect_fixable_security_issues(repo_path, scan_result)
        if not by_file:
            return {"created": False, "reason": "no_fixable_issues", "mode": mode}

        changed_files: List[str] = []
        for file_path, issues in by_file.items():
            if self._apply_java_fixes(file_path, issues):
                changed_files.append(file_path)

        if not changed_files:
            return {"created": False, "reason": "no_changes_applied", "mode": mode}

        branch_name = f"cip/{title_prefix}-security-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        commit_msg = (
            "fix: apply automated Java security remediations\n\n"
            "- add defensive copies for mutable collection accessors\n"
            "- add missing hashCode() where equals() is implemented\n"
        )

        title = "fix: automated remediation for security findings"
        body_lines = [
            "## Automated remediation PR",
            "",
            "This PR was generated automatically from scan findings.",
            "",
            "### What was changed",
            "- Added defensive copies for mutable collection getters/setters (SpotBugs EI_EXPOSE_REP/EI_EXPOSE_REP2).",
            "- Added `hashCode()` where `equals()` is implemented but missing hashCode (HE_EQUALS_USE_HASHCODE).",
            "",
            "### Files changed",
        ]
        for f in changed_files:
            body_lines.append(f"- `{os.path.relpath(f, repo_path)}`")
        body_lines.append("")
        body_lines.append("### Validation")
        body_lines.append("- Please run your project tests and static analysis before merge.")
        body = "\n".join(body_lines)

        return self._commit_push_and_create_pr(
            repo_path=repo_path,
            owner=owner,
            repo=repo,
            changed_files=changed_files,
            base_branch=base_branch,
            branch_name=branch_name,
            commit_msg=commit_msg,
            title=title,
            body=body,
            mode=mode,
            scan_result=scan_result,
        )

