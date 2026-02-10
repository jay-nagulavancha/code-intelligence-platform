"""
Report model - Data models for reports.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class Issue(BaseModel):
    """Model for a single issue."""
    type: str
    severity: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ReportSummary(BaseModel):
    """Summary of scan report."""
    total_issues: int
    by_type: Dict[str, int]
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0


class Recommendation(BaseModel):
    """Recommendation from LLM analysis."""
    title: str
    description: str
    priority: str  # critical, high, medium, low
    action_items: List[str]
    estimated_effort: Optional[str] = None


class Report(BaseModel):
    """Comprehensive report model."""
    summary: ReportSummary
    issues: List[Issue]
    recommendations: List[Recommendation]
    release_notes: Optional[str] = None
    vulnerability_suggestions: Optional[List[Dict[str, Any]]] = None
    deprecation_summary: Optional[Dict[str, Any]] = None
    next_steps: Optional[List[str]] = None
