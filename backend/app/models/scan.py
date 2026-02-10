"""
Scan model - Data models for scans.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class ScanRequest(BaseModel):
    """Request model for initiating a scan."""
    repo_path: str
    scan_types: List[str]
    project_context: Optional[Dict[str, Any]] = None


class ScanResult(BaseModel):
    """Result model for scan execution."""
    scan_id: str
    agents_executed: List[str]
    report: Dict[str, Any]
    raw_results: Dict[str, List[Dict]]
    timestamp: datetime
    historical_context: Optional[Dict[str, Any]] = None
