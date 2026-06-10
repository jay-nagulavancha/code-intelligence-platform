"""
Claude Agent SDK remediation service.

Runs a Claude coding agent against a checked-out repository and returns
changed files plus execution metadata.
"""
import asyncio
import json
import os
import subprocess
from typing import Any, Dict, List, Optional


class ClaudeAgentService:
    """Wrapper around Claude Agent SDK for autonomous remediation."""

    def __init__(self):
        self.enabled = os.getenv("CLAUDE_AGENT_ENABLED", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.permission_mode = os.getenv("CLAUDE_AGENT_PERMISSION_MODE", "acceptEdits")
        self.max_turns = int(os.getenv("CLAUDE_AGENT_MAX_TURNS", "12"))
        self.model = os.getenv("CLAUDE_AGENT_MODEL", "").strip() or None
        self.allowed_tools = [
            t.strip()
            for t in os.getenv("CLAUDE_AGENT_ALLOWED_TOOLS", "Read,Write,Bash").split(",")
            if t.strip()
        ]
        # Forward Bedrock / auth env vars into the Claude Code subprocess so it
        # authenticates the same way as the rest of the platform (e.g. on EC2
        # where CLAUDE_CODE_USE_BEDROCK=1 is set in .env but not in the shell).
        self._subprocess_env: Dict[str, str] = {}
        for var in (
            "CLAUDE_CODE_USE_BEDROCK",
            "AWS_REGION",
            "AWS_DEFAULT_REGION",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "BEDROCK_MODEL_ID",
            "ANTHROPIC_API_KEY",
        ):
            val = os.getenv(var)
            if val:
                self._subprocess_env[var] = val

    @staticmethod
    def _sdk_available() -> bool:
        try:
            import claude_agent_sdk  # noqa: F401

            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        return self.enabled and self._sdk_available()

    @staticmethod
    def _git_changed_files(repo_path: str) -> List[str]:
        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    @staticmethod
    def _build_prompt(file_issue_map: Dict[str, List[Dict[str, Any]]], max_files: int) -> str:
        compact_map: Dict[str, List[Dict[str, Any]]] = {}
        for rel_path in list(file_issue_map.keys())[:max_files]:
            slim_issues = []
            for iss in file_issue_map[rel_path][:5]:
                entry: Dict[str, Any] = {
                    "bug_type": iss.get("bug_type", ""),
                    "severity": iss.get("severity", ""),
                    "line": iss.get("line", ""),
                }
                if iss.get("message"):
                    entry["description"] = iss["message"]
                if iss.get("suggested_fix"):
                    entry["suggested_fix"] = iss["suggested_fix"]
                if iss.get("code_example"):
                    entry["code_example"] = iss["code_example"]
                slim_issues.append(entry)
            compact_map[rel_path] = slim_issues

        return (
            "Apply minimal, safe security fixes for the findings below.\n"
            "Use the 'suggested_fix' and 'code_example' fields as your primary guide when present.\n"
            "Rules:\n"
            "1) Edit only files listed in FINDINGS_BY_FILE.\n"
            "2) Keep behavior intact; avoid broad refactors.\n"
            "3) Do not modify secrets, CI credentials, or deployment keys.\n"
            "4) After edits, run quick validation commands if available.\n"
            "5) Return a short final summary of files changed and why.\n\n"
            f"FINDINGS_BY_FILE:\n{json.dumps(compact_map, indent=2, default=str)}"
        )

    async def _run_query(
        self, repo_path: str, prompt: str, system_prompt: str, max_turns: Optional[int] = None
    ) -> Dict[str, Any]:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

        stderr_lines: List[str] = []

        options = ClaudeAgentOptions(
            cwd=repo_path,
            system_prompt=system_prompt,
            permission_mode=self.permission_mode,
            allowed_tools=self.allowed_tools,
            max_turns=max_turns if max_turns is not None else self.max_turns,
            model=self.model,
            env=self._subprocess_env,
            stderr=lambda line: stderr_lines.append(line),
        )

        result_payload: Optional[ResultMessage] = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    result_payload = message
        except Exception as exc:
            import sys
            if stderr_lines:
                print(f"[claude_agent] stderr:\n" + "\n".join(stderr_lines), file=sys.stderr)
            return {
                "ok": False,
                "reason": str(exc),
                "stderr": stderr_lines,
                "subprocess_env_keys": list(self._subprocess_env.keys()),
                "cwd": repo_path,
            }

        if result_payload is None:
            return {"ok": False, "reason": "no_result_message", "stderr": stderr_lines}
        if result_payload.is_error:
            return {
                "ok": False,
                "reason": "agent_execution_error",
                "subtype": result_payload.subtype,
                "result": result_payload.result,
                "stderr": stderr_lines,
            }

        return {
            "ok": True,
            "summary": result_payload.result or "",
            "subtype": result_payload.subtype,
            "cost_usd": result_payload.total_cost_usd,
            "usage": result_payload.usage,
            "model_usage": result_payload.model_usage,
        }

    # Max files per SDK invocation. Larger batches cause Bedrock context to grow
    # across turns until the session times out (~10+ min). 3 files per batch keeps
    # each call under ~2 minutes and is reliable across all Bedrock regions.
    BATCH_SIZE = 3
    # Max turns per batch. 3 files × ~3 turns each (read+fix+verify) = 9 turns needed.
    # 10 gives headroom without the context-bloat timeout seen at 12 with 10 files.
    BATCH_MAX_TURNS = 10

    def apply_fixes(
        self,
        repo_path: str,
        file_issue_map: Dict[str, List[Dict[str, Any]]],
        max_files: int,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"changed_files": [], "details": [], "reason": "claude_agent_disabled"}
        if not self._sdk_available():
            return {"changed_files": [], "details": [], "reason": "claude_agent_sdk_unavailable"}
        if not file_issue_map:
            return {"changed_files": [], "details": [], "reason": "no_file_scoped_issues"}

        system_prompt = (
            "You are a senior security remediation engineer. "
            "Make minimal, correct, reviewable fixes and preserve existing behavior."
        )

        # Process files in small batches so each SDK call stays within Bedrock's
        # reliable context window (~2 min per batch vs 10+ min for 10 files at once).
        all_files = list(file_issue_map.keys())[:max_files]
        batches = [all_files[i:i + self.BATCH_SIZE] for i in range(0, len(all_files), self.BATCH_SIZE)]

        all_details: List[Dict[str, Any]] = []
        last_agent_result: Optional[Dict[str, Any]] = None

        for batch_files in batches:
            batch_map = {f: file_issue_map[f] for f in batch_files}
            prompt = self._build_prompt(file_issue_map=batch_map, max_files=self.BATCH_SIZE)
            run_result = asyncio.run(self._run_query(
                repo_path=repo_path, prompt=prompt,
                system_prompt=system_prompt, max_turns=self.BATCH_MAX_TURNS,
            ))
            last_agent_result = run_result
            if not run_result.get("ok"):
                import sys
                stderr = run_result.get("stderr", [])
                if stderr:
                    print(f"[claude_agent] stderr:\n" + "\n".join(stderr), file=sys.stderr)
                reason = run_result.get("reason", "")
                # max_turns exhausted with changes is a partial success — keep going.
                # Only log as a warning, not a hard failure.
                print(
                    f"[claude_agent] batch incomplete — files={batch_files} reason={reason}",
                    file=sys.stderr,
                )
                # Continue with remaining batches regardless
                continue

        changed_rel = self._git_changed_files(repo_path)
        details = [
            {
                "file": rel_path,
                "status": "applied",
                "issues_considered": len(file_issue_map.get(rel_path, [])),
            }
            for rel_path in changed_rel
        ]
        return {
            "changed_files": [os.path.join(repo_path, rel) for rel in changed_rel],
            "details": details,
            "reason": None if changed_rel else "no_effective_diff",
            "agent_result": last_agent_result,
        }
