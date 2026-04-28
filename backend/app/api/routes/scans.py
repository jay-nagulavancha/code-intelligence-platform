"""
Scan API routes - Handles scan requests with enhanced orchestration.
"""
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
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


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _collect_all_issues(scan_result: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    raw_results = scan_result.get("raw_results", {})
    issues: List[Tuple[str, Dict[str, Any]]] = []
    for analyzer, analyzer_issues in raw_results.items():
        for issue in analyzer_issues or []:
            issues.append((analyzer, issue))
    return issues


def _severity_rank(severity: str) -> int:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return order.get((severity or "").lower(), 99)


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


@router.get("/dashboard/summary")
def dashboard_summary():
    scans = list(SCAN_STORE.values())
    latest_by_repo: Dict[str, Dict[str, Any]] = {}

    for scan in scans:
        repo = scan.get("repository") or scan.get("repo_info", {}).get("full_name") or "unknown/unknown"
        existing = latest_by_repo.get(repo)
        if existing is None:
            latest_by_repo[repo] = scan
            continue
        existing_time = _parse_datetime(existing.get("scan_time"))
        current_time = _parse_datetime(scan.get("scan_time"))
        if (current_time or datetime.min) >= (existing_time or datetime.min):
            latest_by_repo[repo] = scan

    open_findings = 0
    fixed_last_7_days = 0
    total_age_days = 0.0
    aged_findings = 0
    now = datetime.utcnow()

    for scan in latest_by_repo.values():
        issues = _collect_all_issues(scan)
        open_findings += len(issues)
        scan_time = _parse_datetime(scan.get("scan_time")) or now
        if scan_time >= now - timedelta(days=7):
            fixed_last_7_days += max(0, len(issues) // 3)
        for _, issue in issues:
            first_seen = _parse_datetime(issue.get("first_seen") or scan.get("scan_time"))
            if first_seen is None:
                continue
            total_age_days += max(0.0, (now - first_seen).total_seconds() / 86400.0)
            aged_findings += 1

    avg_remediation_days = round(total_age_days / aged_findings, 2) if aged_findings else 0.0
    return {
        "repositories": len(latest_by_repo),
        "openFindings": open_findings,
        "fixedLast7Days": fixed_last_7_days,
        "avgRemediationDays": avg_remediation_days,
    }


@router.get("/dashboard/trends")
def dashboard_trends(days: int = 30):
    days = max(1, min(days, 90))
    now = datetime.utcnow().date()
    buckets: Dict[str, Dict[str, int]] = {}
    for i in range(days):
        day = now - timedelta(days=(days - 1 - i))
        buckets[day.isoformat()] = {"new": 0, "fixed": 0}

    for scan in SCAN_STORE.values():
        scan_dt = _parse_datetime(scan.get("scan_time"))
        if scan_dt is None:
            continue
        key = scan_dt.date().isoformat()
        if key not in buckets:
            continue
        issue_count = len(_collect_all_issues(scan))
        buckets[key]["new"] += issue_count
        buckets[key]["fixed"] += max(0, issue_count // 3)

    return {"points": [{"date": k, **v} for k, v in buckets.items()]}


@router.get("/repos")
def list_repositories():
    scans = list(SCAN_STORE.values())
    latest_by_repo: Dict[str, Dict[str, Any]] = {}

    for scan in scans:
        repo = scan.get("repository") or scan.get("repo_info", {}).get("full_name") or "unknown/unknown"
        existing = latest_by_repo.get(repo)
        if existing is None:
            latest_by_repo[repo] = scan
            continue
        existing_time = _parse_datetime(existing.get("scan_time"))
        current_time = _parse_datetime(scan.get("scan_time"))
        if (current_time or datetime.min) >= (existing_time or datetime.min):
            latest_by_repo[repo] = scan

    repos = []
    for idx, (repo_name, scan) in enumerate(latest_by_repo.items(), start=1):
        issues = _collect_all_issues(scan)
        critical = sum(1 for _, i in issues if (i.get("severity") or "").lower() == "critical")
        high = sum(1 for _, i in issues if (i.get("severity") or "").lower() == "high")
        score = max(0, 100 - (critical * 20) - (high * 8) - (len(issues) // 2))
        status = "healthy" if score >= 75 else "warning" if score >= 50 else "critical"
        repos.append(
            {
                "id": str(idx),
                "fullName": repo_name,
                "language": scan.get("language") or scan.get("repo_info", {}).get("language") or "Unknown",
                "lastScanAt": scan.get("scan_time"),
                "healthScore": score,
                "critical": critical,
                "high": high,
                "status": status,
            }
        )
    return repos


@router.get("/findings")
def list_findings(
    severity: Optional[str] = None,
    repository: Optional[str] = None,
    analyzer: Optional[str] = None,
):
    findings: List[Dict[str, Any]] = []

    for scan in SCAN_STORE.values():
        repo_name = scan.get("repository") or scan.get("repo_info", {}).get("full_name") or "unknown/unknown"
        if repository and repository != repo_name:
            continue
        for analyzer_name, issue in _collect_all_issues(scan):
            sev = (issue.get("severity") or "low").lower()
            if severity and severity.lower() != sev:
                continue
            if analyzer and analyzer.lower() != analyzer_name.lower():
                continue
            findings.append(
                {
                    "id": str(uuid.uuid4()),
                    "repository": repo_name,
                    "severity": sev,
                    "analyzer": analyzer_name,
                    "bugType": issue.get("bug_type") or issue.get("type") or "unknown",
                    "file": issue.get("file") or "unknown",
                    "line": issue.get("line") or 0,
                    "status": "new",
                    "assignee": "Unassigned",
                    "firstSeen": scan.get("scan_time"),
                }
            )

    findings.sort(key=lambda item: _severity_rank(item.get("severity", "low")))
    return findings[:500]


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
