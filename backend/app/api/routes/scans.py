"""
Scan API routes - Handles scan requests with enhanced orchestration.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from app.services.scan_service import ScanService

router = APIRouter()
scan_service = ScanService()


class ScanRequest(BaseModel):
    """Request model for scan endpoint."""
    repoPath: str
    scanTypes: List[str]
    projectContext: Optional[Dict[str, Any]] = None
    storeInRAG: bool = True


@router.post("/scan")
def scan_repo(request: ScanRequest):
    """
    Run a comprehensive scan using the Orchestrator Agent.
    
    Returns enhanced report with:
    - Agent execution results
    - LLM-generated recommendations
    - Release notes (if changes detected)
    - Vulnerability suggestions (if security issues found)
    - Deprecation summaries (if deprecations found)
    - Historical context from RAG
    """
    try:
        result = scan_service.run_scan(
            repo_path=request.repoPath,
            scan_types=request.scanTypes,
            project_context=request.projectContext,
            store_in_rag=request.storeInRAG
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}")
def get_scan(scan_id: str):
    """Get scan results by ID (future: retrieve from database)."""
    # TODO: Implement retrieval from database
    return {"message": "Not implemented yet", "scan_id": scan_id}
