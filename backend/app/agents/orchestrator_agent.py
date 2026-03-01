"""
Orchestrator Agent - LLM-powered agent that decides which agents to call
and combines their outputs into coherent reports.
Gracefully falls back when LLM is unavailable or slow.
"""
from typing import List, Dict, Optional, Any
import json
from app.agents.security_agent import SecurityAnalyzer
from app.agents.oss_agent import OSSAnalyzer
from app.agents.change_agent import ChangeAnalyzer
from app.agents.deprecation_agent import DeprecationAnalyzer
from app.agents.github_agent import GitHubAnalyzer
from app.services.llm_service import LLMService


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
        return [s for s in scan_types if s in ("security", "oss", "change", "deprecation")]

    def run_agents(
        self,
        repo_path: str,
        agents_to_run: List[str],
    ) -> Dict[str, List[Dict]]:
        """Execute the specified agents and collect their outputs."""
        results = {}

        for agent_name in agents_to_run:
            try:
                if agent_name == "security":
                    results["security"] = self.security_analyzer.run(repo_path)
                elif agent_name == "oss":
                    results["oss"] = self.oss_analyzer.run(repo_path)
                elif agent_name == "change":
                    results["change"] = self.change_analyzer.run(repo_path)
                elif agent_name == "deprecation":
                    results["deprecation"] = self.deprecation_analyzer.run(repo_path)
            except Exception as e:
                results[agent_name] = []
                print(f"{agent_name.title()}Analyzer failed: {e}")

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
                "sample": issues[:5],
            }

        # Strip heavy fields from context to keep prompt small
        ctx = {
            k: v for k, v in project_context.items()
            if k not in ("historical_context", "build_result", "repo_info")
        }

        prompt = f"""Analyze the following scan results and create a report.

Project: {json.dumps(ctx, indent=2, default=str)}

Results (showing up to 5 issues per agent):
{json.dumps(compact, indent=2, default=str)}

Respond with valid JSON containing:
1. summary: key findings (one paragraph)
2. critical_issues: list of issue descriptions needing immediate attention
3. recommendations: list of actionable recommendations
4. next_steps: list of suggested next steps
"""

        try:
            response = self.llm_service.generate(
                prompt=prompt,
                system_prompt=(
                    "You are an expert code analyst. "
                    "Respond ONLY with valid JSON, no markdown fences."
                ),
                max_tokens=512,
            )
            # Extract JSON from response
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

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
        agent_results = self.run_agents(repo_path, agents_to_run)

        if use_llm:
            report = self.combine_outputs(agent_results, project_context)
        else:
            report = self._fallback_report(agent_results)

        return {
            "agents_executed": agents_to_run,
            "report": report,
            "raw_results": agent_results,
        }
