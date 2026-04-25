"""
Scan API routes - Handles scan requests with enhanced orchestration.
"""
import logging
import os
import shutil
import subprocess
import tempfile
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any
from app.services.scan_service import ScanService
from app.agents.pr_agent import PRAgent

logger = logging.getLogger(__name__)

router = APIRouter()
scan_service = ScanService()

# In-memory scan result store keyed by scan_id
SCAN_STORE: Dict[str, Dict[str, Any]] = {}


def store_scan_result(scan_result: Dict[str, Any]) -> None:
    """Store a scan result keyed by its scan_id."""
    scan_id = scan_result.get("scan_id")
    if scan_id:
        SCAN_STORE[scan_id] = scan_result


def get_scan_result(scan_id: str) -> Optional[Dict[str, Any]]:
    """Return the scan result for scan_id, or None if absent."""
    return SCAN_STORE.get(scan_id)


class RemediateRequest(BaseModel):
    remediation_mode: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    base_branch: str = "main"

    @field_validator("remediation_mode")
    @classmethod
    def validate_mode(cls, v):
        if v is not None and v not in ("deterministic", "nondeterministic"):
            raise ValueError("remediation_mode must be 'deterministic' or 'nondeterministic'")
        return v


class RemediateResponse(BaseModel):
    scan_id: str
    created: bool
    mode: str
    branch: Optional[str] = None
    pull_request: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


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
        store_scan_result(result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}")
def get_scan(scan_id: str):
    """Get scan results by ID."""
    result = get_scan_result(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
    return result


@router.post("/scan/{scan_id}/remediate", response_model=RemediateResponse)
def remediate_scan(scan_id: str, request: RemediateRequest):
    """
    Trigger remediation for a previously stored scan result.

    Clones the repository, invokes PRAgent.create_fix_pr(), and returns
    a RemediateResponse describing the outcome.
    """
    # 4.2 Look up scan_id in SCAN_STORE; raise 404 if absent
    scan_result = get_scan_result(scan_id)
    if scan_result is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    # 4.3 Resolve owner and repo
    owner = request.owner
    repo = request.repo
    if not owner or not repo:
        repository = scan_result.get("repository", "")
        if "/" in repository:
            parts = repository.split("/", 1)
            owner = owner or parts[0]
            repo = repo or parts[1]
    if not owner or not repo:
        raise HTTPException(
            status_code=422,
            detail="owner and repo are required but could not be resolved from the scan result",
        )

    # 4.4 Resolve remediation_mode
    mode = request.remediation_mode or os.getenv("REMEDIATION_MODE", "deterministic")

    # 4.5 Log before invoking PRAgent
    logger.info(
        "Starting remediation: scan_id=%s owner/repo=%s/%s remediation_mode=%s",
        scan_id, owner, repo, mode,
    )

    # 4.6 Clone the repository to a temp directory
    temp_dir = tempfile.mkdtemp(prefix=f"remediate_{owner}_{repo}_")
    clone_url = f"https://github.com/{owner}/{repo}.git"
    clone_result = subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, temp_dir],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if clone_result.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clone repository: {clone_result.stderr}",
        )

    # 4.7 Instantiate PRAgent and call create_fix_pr inside try/except/finally
    try:
        pr_result = PRAgent().create_fix_pr(
            repo_path=temp_dir,
            owner=owner,
            repo=repo,
            scan_result=scan_result,
            base_branch=request.base_branch,
            remediation_mode=mode,
        )
        # 4.9 On success, log and return RemediateResponse
        logger.info(
            "Remediation complete: scan_id=%s created=%s mode=%s reason=%s",
            scan_id, pr_result.get("created"), pr_result.get("mode"), pr_result.get("reason"),
        )
        return RemediateResponse(
            scan_id=scan_id,
            created=pr_result["created"],
            mode=pr_result["mode"],
            branch=pr_result.get("branch"),
            pull_request=pr_result.get("pull_request"),
            reason=pr_result.get("reason"),
        )
    except Exception as e:
        # 4.10 On exception, log at ERROR and raise HTTP 500
        logger.error("Remediation failed: scan_id=%s error=%s", scan_id, e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 4.8 Always clean up the temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
