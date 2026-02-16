"""
Scan Service - Orchestrates the full scan pipeline:
  1. RAG historical context retrieval
  2. Agent orchestration (security, oss, change, deprecation)
  3. LLM enhancement (fix suggestions, summaries, release notes)
  4. RAG storage for future queries
  5. GitHub issue creation for critical/high findings
"""
import os
import uuid
import tempfile
import shutil
import subprocess
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.github_agent import GitHubAgent
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.mcp_github_service import MCPGitHubService
from app.utils.project_detector import ProjectDetector
from app.utils.project_builder import ProjectBuilder


class ScanService:
    """
    Full-pipeline scan service that uses Orchestrator Agent for intelligent
    agent selection and combines outputs with LLM, RAG, and GitHub integration.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        rag_service: Optional[RAGService] = None,
        github_service: Optional[MCPGitHubService] = None,
    ):
        self.llm_service = llm_service or LLMService()
        self.rag_service = rag_service  # Can be None (--no-rag)
        self.github_service = github_service or MCPGitHubService()
        self.github_agent = GitHubAgent(self.github_service)
        self.orchestrator = OrchestratorAgent(llm_service=self.llm_service)
        self.detector = ProjectDetector()
        self.builder = ProjectBuilder()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_scan(
        self,
        repo_path: str,
        scan_types: List[str],
        project_context: Optional[Dict[str, Any]] = None,
        store_in_rag: bool = True,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a comprehensive scan on a local repository path.

        Steps executed:
          1. Query RAG for historical context
          2. Orchestrate agents (decide → run → combine)
          3. Enhance report with LLM (fix suggestions, summaries)
          4. Store results in RAG
        """
        if project_context is None:
            project_context = {
                "name": os.path.basename(repo_path),
                "path": repo_path,
            }

        scan_id = str(uuid.uuid4())
        project_context["scan_id"] = scan_id
        project_context["scan_time"] = datetime.utcnow().isoformat()

        # --- Step 1: RAG historical context ---
        historical_context = self._query_rag(project_context)
        if historical_context:
            project_context["historical_context"] = historical_context

        # --- Step 2: Orchestrate agents ---
        result = self.orchestrator.orchestrate(
            repo_path=repo_path,
            scan_types=scan_types,
            project_context=project_context,
            use_llm=use_llm,
        )

        # --- Step 3: LLM enhancement (optional) ---
        if use_llm:
            enhanced_result = self._enhance_with_llm(result, project_context)
        else:
            result.setdefault("llm_enhanced", False)
            enhanced_result = result

        # --- Step 4: Store in RAG ---
        if store_in_rag:
            self._store_in_rag(scan_id, enhanced_result, project_context)

        enhanced_result["scan_id"] = scan_id
        enhanced_result["historical_context"] = historical_context
        return enhanced_result

    def scan_github_repo(
        self,
        owner: str,
        repo: str,
        scan_types: Optional[List[str]] = None,
        create_issues: bool = True,
        store_in_rag: bool = True,
        use_llm: bool = True,
        on_progress: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Full end-to-end pipeline for scanning a GitHub repository.

        Steps executed:
          1. Fetch repository metadata via GitHub API
          2. Clone repository locally
          3. Detect language & build (for Java)
          4. Run full scan pipeline (agents → LLM → RAG)
          5. Create GitHub Issues for critical/high findings
          6. Clean up temporary clone

        Args:
            owner: GitHub repository owner
            repo: GitHub repository name
            scan_types: Scan types to run (default: ["security", "oss"])
            create_issues: Whether to create GitHub issues for findings
            store_in_rag: Whether to store results in RAG
            on_progress: Optional callback(step: int, message: str) for progress

        Returns:
            Full enhanced scan report
        """
        if scan_types is None:
            scan_types = ["security", "oss"]

        def progress(step: int, msg: str):
            if on_progress:
                on_progress(step, msg)

        # --- Step 1: Fetch repo info ---
        progress(1, "Fetching repository information...")
        repo_info = self._fetch_repo_info(owner, repo)

        # --- Step 2: Clone ---
        progress(2, "Cloning repository...")
        temp_dir = self._clone_repository(owner, repo)

        try:
            # --- Step 3: Detect language & build ---
            progress(3, "Detecting language and building project...")
            language = self.detector.get_primary_language(temp_dir)
            build_result = None
            if language == "java":
                build_result = self.builder.build(temp_dir)

            project_context = {
                "name": repo,
                "owner": owner,
                "full_name": f"{owner}/{repo}",
                "language": language,
                "github_url": f"https://github.com/{owner}/{repo}",
                "description": repo_info.get("description"),
                "default_branch": repo_info.get("default_branch", "main"),
                "build_result": build_result,
            }

            # --- Step 4: Full scan pipeline ---
            llm_label = " + LLM" if use_llm else ""
            rag_label = " + RAG" if store_in_rag else ""
            progress(4, f"Running scan pipeline (agents{llm_label}{rag_label})...")
            result = self.run_scan(
                repo_path=temp_dir,
                scan_types=scan_types,
                project_context=project_context,
                store_in_rag=store_in_rag,
                use_llm=use_llm,
            )

            result["repository"] = f"{owner}/{repo}"
            result["language"] = language
            result["build_result"] = build_result
            result["repo_info"] = repo_info

            # --- Step 5: Create GitHub Issues ---
            if create_issues:
                progress(5, "Creating GitHub issues for critical/high findings...")
                created_issues = self._create_github_issues(owner, repo, result)
                result["github_issues_created"] = created_issues
            else:
                progress(5, "Skipping GitHub issue creation (--no-issues)")

            return result

        finally:
            # --- Step 6: Cleanup ---
            progress(6, "Cleaning up temporary files...")
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_rag(self, project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Query RAG for historical context, returns empty dict on failure."""
        if self.rag_service is None:
            return {}
        try:
            if self.rag_service.is_available():
                return self.rag_service.get_historical_context(
                    current_issues=[],
                    project_context=project_context,
                )
        except Exception as e:
            print(f"RAG query failed (non-fatal): {e}")
        return {}

    def _store_in_rag(
        self,
        scan_id: str,
        result: Dict[str, Any],
        project_context: Dict[str, Any],
    ):
        """Persist scan results into RAG for future queries."""
        if self.rag_service is None:
            return
        try:
            if self.rag_service.is_available():
                all_issues = result.get("report", {}).get("raw_issues", [])
                self.rag_service.store_scan(
                    scan_id=scan_id,
                    issues=all_issues,
                    project_context=project_context,
                    code_snippets=None,
                )
        except Exception as e:
            print(f"RAG storage failed (non-fatal): {e}")

    def _enhance_with_llm(
        self,
        result: Dict[str, Any],
        project_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Enhance scan results with LLM-generated content."""
        if not self.llm_service.is_available():
            result.setdefault("llm_enhanced", False)
            return result

        report = result.get("report", {})
        raw_results = result.get("raw_results", {})

        # Generate release notes if changes are present
        if "change" in raw_results and raw_results["change"]:
            try:
                release_notes = self.llm_service.generate_release_notes(
                    changes=raw_results["change"],
                    issues=report.get("raw_issues", []),
                    project_context=project_context,
                )
                report["release_notes"] = release_notes
            except Exception as e:
                print(f"Failed to generate release notes: {e}")

        # Suggest fixes for vulnerabilities
        if "security" in raw_results and raw_results["security"]:
            try:
                suggestions = self.llm_service.suggest_vulnerability_fixes(
                    vulnerabilities=raw_results["security"]
                )
                report["vulnerability_suggestions"] = suggestions
            except Exception as e:
                print(f"Failed to generate vulnerability suggestions: {e}")

        # Summarize deprecation issues
        if "deprecation" in raw_results and raw_results["deprecation"]:
            try:
                summary = self.llm_service.summarize_deprecation_issues(
                    deprecation_issues=raw_results["deprecation"]
                )
                report["deprecation_summary"] = summary
            except Exception as e:
                print(f"Failed to generate deprecation summary: {e}")

        result["report"] = report
        result["llm_enhanced"] = True
        return result

    def _fetch_repo_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch repository metadata from GitHub API."""
        if not self.github_service.is_available():
            return {"full_name": f"{owner}/{repo}"}
        try:
            return self.github_service.get_repository(owner, repo)
        except Exception as e:
            print(f"Failed to fetch repo info: {e}")
            return {"full_name": f"{owner}/{repo}"}

    def _clone_repository(self, owner: str, repo: str) -> str:
        """Clone a GitHub repository to a temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix=f"scan_{owner}_{repo}_")
        token = self.github_service.github_token or ""
        if token:
            clone_url = f"https://{token}@github.com/{owner}/{repo}.git"
        else:
            clone_url = f"https://github.com/{owner}/{repo}.git"

        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr}")
            return temp_dir
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to clone repository: {e}")

    # ------------------------------------------------------------------
    # GitHub Issue creation
    # ------------------------------------------------------------------

    def _create_github_issues(
        self,
        owner: str,
        repo: str,
        scan_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Create GitHub Issues for critical and high severity findings.
        Groups related findings into a single summary issue.
        """
        if not self.github_service.is_available():
            return []

        raw_results = scan_result.get("raw_results", {})
        report = scan_result.get("report", {})
        scan_id = scan_result.get("scan_id", "unknown")

        # Collect critical/high issues from all agents
        critical_issues = []
        high_issues = []
        medium_issues = []

        for agent_type, issues in raw_results.items():
            for issue in issues:
                severity = (issue.get("severity") or "").lower()
                if severity == "critical":
                    critical_issues.append({**issue, "agent": agent_type})
                elif severity == "high":
                    high_issues.append({**issue, "agent": agent_type})
                elif severity == "medium":
                    medium_issues.append({**issue, "agent": agent_type})

        created = []

        # Create a summary issue if there are critical or high findings
        if critical_issues or high_issues:
            body = self._build_issue_body(
                scan_id=scan_id,
                critical_issues=critical_issues,
                high_issues=high_issues,
                medium_count=len(medium_issues),
                report=report,
                scan_result=scan_result,
            )

            severity_tag = "CRITICAL" if critical_issues else "HIGH"
            title = (
                f"[{severity_tag}] Security Scan: "
                f"{len(critical_issues)} critical, "
                f"{len(high_issues)} high findings"
            )

            labels = ["code-intelligence", "security"]
            if critical_issues:
                labels.append("critical")

            try:
                issue = self.github_service.create_issue(
                    owner=owner,
                    repo=repo,
                    title=title,
                    body=body,
                    labels=labels,
                )
                created.append(issue)
            except Exception as e:
                print(f"Failed to create GitHub issue: {e}")

        return created

    def _build_issue_body(
        self,
        scan_id: str,
        critical_issues: List[Dict],
        high_issues: List[Dict],
        medium_count: int,
        report: Dict[str, Any],
        scan_result: Dict[str, Any],
    ) -> str:
        """Build a well-formatted GitHub Issue body from scan findings."""
        lines = []
        lines.append("## Code Intelligence Platform — Scan Report")
        lines.append("")
        lines.append(f"**Scan ID:** `{scan_id}`")
        lines.append(f"**Repository:** {scan_result.get('repository', 'N/A')}")
        lines.append(f"**Language:** {scan_result.get('language', 'N/A')}")
        lines.append(f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")

        # Summary table
        lines.append("### Summary")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| Critical | {len(critical_issues)} |")
        lines.append(f"| High     | {len(high_issues)} |")
        lines.append(f"| Medium   | {medium_count} |")
        lines.append("")

        # Critical findings
        if critical_issues:
            lines.append("### Critical Findings")
            lines.append("")
            for i, issue in enumerate(critical_issues[:15], 1):
                msg = issue.get("message", "Unknown issue")
                file_path = issue.get("file") or ""
                line_no = issue.get("line") or ""
                tool = issue.get("tool", issue.get("agent", ""))
                loc = f" (`{file_path}:{line_no}`)" if file_path else ""
                lines.append(f"{i}. **{msg}**{loc}")
                if tool:
                    lines.append(f"   - Tool: {tool}")
            lines.append("")

        # High findings
        if high_issues:
            lines.append("### High Findings")
            lines.append("")
            for i, issue in enumerate(high_issues[:15], 1):
                msg = issue.get("message", "Unknown issue")
                file_path = issue.get("file") or ""
                line_no = issue.get("line") or ""
                tool = issue.get("tool", issue.get("agent", ""))
                loc = f" (`{file_path}:{line_no}`)" if file_path else ""
                lines.append(f"{i}. **{msg}**{loc}")
                if tool:
                    lines.append(f"   - Tool: {tool}")
            lines.append("")

        # LLM-generated fix suggestions (if available)
        suggestions = report.get("vulnerability_suggestions", [])
        if suggestions:
            lines.append("### Recommended Fixes (AI-Generated)")
            lines.append("")
            for i, sug in enumerate(suggestions[:10], 1):
                explanation = sug.get("explanation", sug.get("issue", ""))
                fix = sug.get("fix", sug.get("code_fix", sug.get("suggestion", "")))
                lines.append(f"**{i}. {explanation}**")
                if fix:
                    lines.append(f"```")
                    lines.append(fix)
                    lines.append(f"```")
                lines.append("")

        # LLM recommendations
        recommendations = report.get("recommendations", [])
        if recommendations and isinstance(recommendations, list):
            lines.append("### Recommendations")
            lines.append("")
            for rec in recommendations[:5]:
                if isinstance(rec, dict):
                    lines.append(f"- {rec.get('title', rec.get('recommendation', str(rec)))}")
                else:
                    lines.append(f"- {rec}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by Code Intelligence Platform*")
        return "\n".join(lines)
