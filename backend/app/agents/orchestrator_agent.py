"""
Orchestrator Agent - LLM-powered agent that decides which agents to call
and combines their outputs into coherent reports.
Gracefully falls back when LLM is unavailable or slow.
"""
from typing import List, Dict, Optional, Any, Callable
import json
import logging
from app.agents.security_agent import SecurityAnalyzer
from app.agents.oss_agent import OSSAnalyzer
from app.agents.change_agent import ChangeAnalyzer
from app.agents.deprecation_agent import DeprecationAnalyzer
from app.agents.secrets_agent import SecretsAnalyzer
from app.agents.infra_agent import InfraAnalyzer
from app.agents.container_agent import ContainerAnalyzer
from app.agents.github_agent import GitHubAnalyzer
from app.services.llm_service import LLMService


logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    Orchestrator Agent that uses LLM to:
    1. Decide which agents to call based on scan types and project context
    2. Combine agent outputs into coherent reports
    3. Generate recommendations

    Every LLM call is wrapped in a try/except so a slow or broken LLM
    never blocks the scan pipeline.
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or LLMService()
        self.security_analyzer = SecurityAnalyzer()
        self.oss_analyzer = OSSAnalyzer()
        self.change_analyzer = ChangeAnalyzer()
        self.deprecation_analyzer = DeprecationAnalyzer()
        self.secrets_analyzer = SecretsAnalyzer()
        self.infra_analyzer = InfraAnalyzer()
        self.container_analyzer = ContainerAnalyzer()
        self.github_analyzer = GitHubAnalyzer()

    def decide_agents(
        self,
        scan_types: List[str],
        project_context: Dict[str, Any],
    ) -> List[str]:
        """
        Decide which agents to run. Uses scan_types directly (fast path).
        LLM-based decision is optional and only used to *filter out*
        irrelevant agents — never to block.
        """
        # Fast path: always honour the explicit scan_types
        supported = (
            "security",
            "oss",
            "change",
            "deprecation",
            "secrets",
            "infra",
            "container",
        )
        return [s for s in scan_types if s in supported]

    def run_agents(
        self,
        repo_path: str,
        agents_to_run: List[str],
        on_agent_completed: Optional[Callable[[str, List[Dict]], None]] = None,
    ) -> Dict[str, List[Dict]]:
        """Execute the specified agents and collect their outputs."""
        results = {}
        tool_map = {
            "security": ["bandit", "semgrep", "spotbugs"],
            "oss": ["dependency-check", "pip-licenses"],
            "change": ["git-diff"],
            "deprecation": ["ast-deprecation-scanner"],
            "secrets": ["gitleaks"],
            "infra": ["checkov"],
            "container": ["trivy"],
        }

        for agent_name in agents_to_run:
            try:
                tools = tool_map.get(agent_name, [])
                logger.info(
                    "Running analyzer '%s' with tool(s): %s",
                    agent_name,
                    ", ".join(tools) if tools else "unknown",
                )
                if agent_name == "security":
                    results["security"] = self.security_analyzer.run(repo_path)
                elif agent_name == "oss":
                    results["oss"] = self.oss_analyzer.run(repo_path)
                elif agent_name == "change":
                    results["change"] = self.change_analyzer.run(repo_path)
                elif agent_name == "deprecation":
                    results["deprecation"] = self.deprecation_analyzer.run(repo_path)
                elif agent_name == "secrets":
                    results["secrets"] = self.secrets_analyzer.run(repo_path)
                elif agent_name == "infra":
                    results["infra"] = self.infra_analyzer.run(repo_path)
                elif agent_name == "container":
                    results["container"] = self.container_analyzer.run(repo_path)
                if on_agent_completed is not None:
                    on_agent_completed(agent_name, results.get(agent_name, []))
            except Exception as e:
                results[agent_name] = []
                print(f"{agent_name.title()}Analyzer failed: {e}")
                if on_agent_completed is not None:
                    on_agent_completed(agent_name, [])

        return results

    def _fallback_report(
        self,
        agent_results: Dict[str, List[Dict]],
    ) -> Dict[str, Any]:
        """Build a structured report without using the LLM."""
        all_issues = []
        for issues in agent_results.values():
            all_issues.extend(issues)

        by_severity: Dict[str, int] = {}
        for issue in all_issues:
            sev = (issue.get("severity") or "unknown").lower()
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "summary": {
                "total_issues": len(all_issues),
                "by_type": {k: len(v) for k, v in agent_results.items()},
                "by_severity": by_severity,
            },
            "raw_issues": all_issues,
            "recommendations": [],
        }

    def combine_outputs(
        self,
        agent_results: Dict[str, List[Dict]],
        project_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Combine agent outputs into a report. Tries the LLM for a richer
        report but always falls back to a structured summary if the LLM
        is unavailable, slow, or returns unparseable output.
        """
        fallback = self._fallback_report(agent_results)

        if not self.llm_service.is_available():
            return fallback

        # Build a compact summary for the LLM (avoid sending huge payloads)
        compact = {}
        for agent_type, issues in agent_results.items():
            compact[agent_type] = {
                "count": len(issues),
                # Only send 3 issues max, and strip heavy fields to keep prompt small
                "sample": [
                    {k: v for k, v in i.items()
                     if k in ("message", "severity", "file", "line", "bug_type", "package", "type")}
                    for i in issues[:3]
                ],
            }

        # Strip heavy fields from context to keep prompt small
        ctx = {
            k: v for k, v in project_context.items()
            if k not in ("historical_context", "build_result", "repo_info")
        }

        prompt = f"""Analyze the following scan results and create a concise report.

Project: {json.dumps(ctx, indent=2, default=str)}

Results (showing up to 3 issues per agent):
{json.dumps(compact, indent=2, default=str)}

Respond with valid JSON only (no markdown, no explanation) containing exactly these keys:
{{"summary": "one paragraph of key findings",
  "critical_issues": ["issue description 1", "issue description 2"],
  "recommendations": ["recommendation 1", "recommendation 2"],
  "next_steps": ["next step 1", "next step 2"]}}
Keep each list to 3 items maximum. Be concise."""

        try:
            response = self.llm_service.generate(
                prompt=prompt,
                system_prompt=(
                    "You are an expert code analyst. "
                    "Respond ONLY with valid compact JSON. No markdown fences. No extra text."
                ),
                max_tokens=1024,
            )
            # Extract JSON from response
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            # Find the outermost JSON object in case the model added extra text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]

            report = json.loads(text)
            report["raw_issues"] = fallback["raw_issues"]
            report.setdefault("summary", fallback["summary"])
            return report
        except Exception as e:
            print(f"LLM report generation failed ({e}), using fallback")
            return fallback

    def orchestrate(
        self,
        repo_path: str,
        scan_types: List[str],
        project_context: Optional[Dict[str, Any]] = None,
        use_llm: bool = True,
        on_agent_completed: Optional[Callable[[str, List[Dict]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Main orchestration:
        1. Decide which agents to run (fast, no LLM)
        2. Execute agents
        3. Combine outputs (LLM with fallback, or just fallback if use_llm=False)
        """
        if project_context is None:
            project_context = {}

        agents_to_run = self.decide_agents(scan_types, project_context)
        agent_results = self.run_agents(
            repo_path=repo_path,
            agents_to_run=agents_to_run,
            on_agent_completed=on_agent_completed,
        )

        if use_llm:
            report = self.combine_outputs(agent_results, project_context)
        else:
            report = self._fallback_report(agent_results)

        return {
            "agents_executed": agents_to_run,
            "report": report,
            "raw_results": agent_results,
        }
