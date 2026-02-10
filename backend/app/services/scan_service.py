"""
Scan Service - Orchestrates scans using the Orchestrator Agent
with LLM and RAG integration.
"""
from typing import List, Dict, Any, Optional
from app.agents.orchestrator_agent import OrchestratorAgent
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
import uuid


class ScanService:
    """
    Enhanced scan service that uses Orchestrator Agent for intelligent
    agent selection and combines outputs with LLM and RAG.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        rag_service: Optional[RAGService] = None
    ):
        self.llm_service = llm_service or LLMService()
        self.rag_service = rag_service or RAGService()
        self.orchestrator = OrchestratorAgent(llm_service=self.llm_service)

    def run_scan(
        self, 
        repo_path: str, 
        scan_types: List[str],
        project_context: Optional[Dict[str, Any]] = None,
        store_in_rag: bool = True
    ) -> Dict[str, Any]:
        """
        Run a comprehensive scan using the Orchestrator Agent.
        
        Args:
            repo_path: Path to the repository
            scan_types: List of scan types requested
            project_context: Additional project context
            store_in_rag: Whether to store results in RAG for future queries
        
        Returns:
            Comprehensive scan report with recommendations
        """
        if project_context is None:
            project_context = {
                "name": repo_path.split("/")[-1],
                "path": repo_path
            }

        # Get historical context from RAG
        historical_context = {}
        if self.rag_service.is_available():
            # Query for similar historical scans (using empty list as placeholder)
            historical_context = self.rag_service.get_historical_context(
                current_issues=[],
                project_context=project_context
            )
            # Add historical context to project context
            project_context["historical_context"] = historical_context

        # Run orchestration
        scan_id = str(uuid.uuid4())
        result = self.orchestrator.orchestrate(
            repo_path=repo_path,
            scan_types=scan_types,
            project_context=project_context
        )

        # Enhance with LLM-generated content
        enhanced_result = self._enhance_with_llm(result, project_context)

        # Store in RAG for future queries
        if store_in_rag and self.rag_service.is_available():
            all_issues = enhanced_result.get("report", {}).get("raw_issues", [])
            self.rag_service.store_scan(
                scan_id=scan_id,
                issues=all_issues,
                project_context=project_context,
                code_snippets=None  # Could extract code snippets from issues
            )

        enhanced_result["scan_id"] = scan_id
        enhanced_result["historical_context"] = historical_context

        return enhanced_result

    def _enhance_with_llm(
        self, 
        result: Dict[str, Any], 
        project_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance scan results with LLM-generated content."""
        if not self.llm_service.is_available():
            return result

        report = result.get("report", {})
        raw_results = result.get("raw_results", {})

        # Generate release notes if changes are present
        if "change" in raw_results:
            changes = raw_results["change"]
            issues = report.get("raw_issues", [])
            try:
                release_notes = self.llm_service.generate_release_notes(
                    changes=changes,
                    issues=issues,
                    project_context=project_context
                )
                report["release_notes"] = release_notes
            except Exception as e:
                print(f"Failed to generate release notes: {e}")

        # Suggest fixes for vulnerabilities
        if "security" in raw_results:
            vulnerabilities = raw_results["security"]
            try:
                suggestions = self.llm_service.suggest_vulnerability_fixes(
                    vulnerabilities=vulnerabilities
                )
                report["vulnerability_suggestions"] = suggestions
            except Exception as e:
                print(f"Failed to generate vulnerability suggestions: {e}")

        # Summarize deprecation issues
        if "deprecation" in raw_results:
            deprecation_issues = raw_results["deprecation"]
            try:
                deprecation_summary = self.llm_service.summarize_deprecation_issues(
                    deprecation_issues=deprecation_issues
                )
                report["deprecation_summary"] = deprecation_summary
            except Exception as e:
                print(f"Failed to generate deprecation summary: {e}")

        result["report"] = report
        return result
