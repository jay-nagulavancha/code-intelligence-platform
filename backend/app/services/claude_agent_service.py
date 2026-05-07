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
            compact_map[rel_path] = file_issue_map[rel_path][:5]

        return (
            "Apply minimal, safe security fixes for the findings below.\n"
            "Rules:\n"
            "1) Edit only files listed in FINDINGS_BY_FILE.\n"
            "2) Keep behavior intact; avoid broad refactors.\n"
            "3) Do not modify secrets, CI credentials, or deployment keys.\n"
            "4) After edits, run quick validation commands if available.\n"
            "5) Return a short final summary of files changed and why.\n\n"
            f"FINDINGS_BY_FILE:\n{json.dumps(compact_map, indent=2, default=str)}"
        )

    async def _run_query(self, repo_path: str, prompt: str, system_prompt: str) -> Dict[str, Any]:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

        options = ClaudeAgentOptions(
            cwd=repo_path,
            system_prompt=system_prompt,
            permission_mode=self.permission_mode,
            allowed_tools=self.allowed_tools,
            max_turns=self.max_turns,
            model=self.model,
        )

        result_payload: Optional[ResultMessage] = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result_payload = message

        if result_payload is None:
            return {"ok": False, "reason": "no_result_message"}
        if result_payload.is_error:
            return {
                "ok": False,
                "reason": "agent_execution_error",
                "subtype": result_payload.subtype,
                "result": result_payload.result,
            }

        return {
            "ok": True,
            "summary": result_payload.result or "",
            "subtype": result_payload.subtype,
            "cost_usd": result_payload.total_cost_usd,
            "usage": result_payload.usage,
            "model_usage": result_payload.model_usage,
        }

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

        prompt = self._build_prompt(file_issue_map=file_issue_map, max_files=max_files)
        system_prompt = (
            "You are a senior security remediation engineer. "
            "Make minimal, correct, reviewable fixes and preserve existing behavior."
        )
        run_result = asyncio.run(self._run_query(repo_path=repo_path, prompt=prompt, system_prompt=system_prompt))
        if not run_result.get("ok"):
            return {
                "changed_files": [],
                "details": [],
                "reason": run_result.get("reason", "agent_failed"),
                "agent_result": run_result,
            }

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
            "agent_result": run_result,
        }
