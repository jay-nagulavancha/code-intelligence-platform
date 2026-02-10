"""
Orchestrator Agent - LLM-powered agent that decides which agents to call
and combines their outputs into coherent reports.
"""
from typing import List, Dict, Optional, Any
import json
from app.agents.security_agent import SecurityAgent
from app.agents.oss_agent import OSSAgent
from app.agents.change_agent import ChangeAgent
from app.agents.deprecation_agent import DeprecationAgent
from app.agents.github_agent import GitHubAgent
from app.services.llm_service import LLMService


class OrchestratorAgent:
    """
    Orchestrator Agent that uses LLM to:
    1. Decide which agents to call based on scan types and project context
    2. Combine agent outputs into coherent reports
    3. Generate recommendations
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or LLMService()
        self.security_agent = SecurityAgent()
        self.oss_agent = OSSAgent()
        self.change_agent = ChangeAgent()
        self.deprecation_agent = DeprecationAgent()
        self.github_agent = GitHubAgent()

    def decide_agents(
        self, 
        scan_types: List[str], 
        project_context: Dict[str, Any]
    ) -> List[str]:
        """
        Uses LLM to decide which agents to call based on scan types and context.
        Falls back to direct mapping if LLM is unavailable.
        """
        if not self.llm_service.is_available():
            # Fallback: use scan_types directly
            return scan_types

        prompt = f"""Based on the following scan request and project context, determine which agents should be executed.

Scan Types Requested: {', '.join(scan_types)}
Project Context: {json.dumps(project_context, indent=2)}

Available Agents:
- security: Security vulnerability scanning (Bandit)
- oss: Open source license scanning (pip-licenses)
- change: Code change analysis (git diff)
- deprecation: Deprecated code detection (AST rules)

Respond with a JSON array of agent names to execute, e.g., ["security", "oss"].
Only include agents that are relevant and requested."""

        try:
            response = self.llm_service.generate(
                prompt=prompt,
                system_prompt="You are an intelligent agent orchestrator. Respond only with valid JSON arrays."
            )
            # Parse JSON response
            agents = json.loads(response.strip())
            if isinstance(agents, list):
                return agents
        except Exception as e:
            print(f"LLM decision failed: {e}, falling back to scan_types")
        
        return scan_types

    def run_agents(
        self, 
        repo_path: str, 
        agents_to_run: List[str]
    ) -> Dict[str, List[Dict]]:
        """Execute the specified agents and collect their outputs."""
        results = {}

        if "security" in agents_to_run:
            try:
                results["security"] = self.security_agent.run(repo_path)
            except Exception as e:
                results["security"] = []
                print(f"SecurityAgent failed: {e}")

        if "oss" in agents_to_run:
            try:
                results["oss"] = self.oss_agent.run(repo_path)
            except Exception as e:
                results["oss"] = []
                print(f"OSSAgent failed: {e}")

        if "change" in agents_to_run:
            try:
                results["change"] = self.change_agent.run(repo_path)
            except Exception as e:
                results["change"] = []
                print(f"ChangeAgent failed: {e}")

        if "deprecation" in agents_to_run:
            try:
                results["deprecation"] = self.deprecation_agent.run(repo_path)
            except Exception as e:
                results["deprecation"] = []
                print(f"DeprecationAgent failed: {e}")

        return results

    def combine_outputs(
        self, 
        agent_results: Dict[str, List[Dict]], 
        project_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Uses LLM to combine agent outputs into a coherent report with recommendations.
        """
        # Flatten all issues
        all_issues = []
        for agent_type, issues in agent_results.items():
            all_issues.extend(issues)

        if not self.llm_service.is_available():
            # Fallback: simple combination
            return {
                "summary": {
                    "total_issues": len(all_issues),
                    "by_type": {k: len(v) for k, v in agent_results.items()}
                },
                "issues": all_issues,
                "recommendations": []
            }

        prompt = f"""Analyze the following scan results and create a comprehensive report.

Project Context: {json.dumps(project_context, indent=2)}

Scan Results:
{json.dumps(agent_results, indent=2)}

Provide a JSON response with:
1. summary: Overall statistics and key findings
2. critical_issues: List of critical issues that need immediate attention
3. recommendations: Actionable recommendations prioritized by importance
4. next_steps: Suggested next steps for the development team

Format your response as valid JSON."""

        try:
            response = self.llm_service.generate(
                prompt=prompt,
                system_prompt="You are an expert code analyst. Provide structured, actionable insights in JSON format."
            )
            report = json.loads(response.strip())
            report["raw_issues"] = all_issues
            return report
        except Exception as e:
            print(f"LLM combination failed: {e}, using fallback")
            return {
                "summary": {
                    "total_issues": len(all_issues),
                    "by_type": {k: len(v) for k, v in agent_results.items()}
                },
                "issues": all_issues,
                "recommendations": []
            }

    def orchestrate(
        self, 
        repo_path: str, 
        scan_types: List[str], 
        project_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main orchestration method that:
        1. Decides which agents to run
        2. Executes them
        3. Combines outputs into a coherent report
        """
        if project_context is None:
            project_context = {}

        # Step 1: Decide which agents to run
        agents_to_run = self.decide_agents(scan_types, project_context)
        
        # Step 2: Run the agents
        agent_results = self.run_agents(repo_path, agents_to_run)
        
        # Step 3: Combine outputs
        report = self.combine_outputs(agent_results, project_context)
        
        return {
            "agents_executed": agents_to_run,
            "report": report,
            "raw_results": agent_results
        }
