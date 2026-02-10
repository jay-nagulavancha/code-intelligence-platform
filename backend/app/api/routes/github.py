"""
GitHub API routes - Handles GitHub repository interactions via MCP.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from app.agents.github_agent import GitHubAgent
from app.services.mcp_github_service import MCPGitHubService

router = APIRouter()
github_agent = GitHubAgent()


class GitHubRepositoryRequest(BaseModel):
    """Request model for GitHub repository operations."""
    owner: str
    repo: str
    include_files: bool = False
    include_issues: bool = False
    include_commits: bool = False


class GitHubScanRequest(BaseModel):
    """Request model for scanning GitHub repository."""
    owner: str
    repo: str
    scan_types: List[str]


class CreateIssueRequest(BaseModel):
    """Request model for creating GitHub issue."""
    owner: str
    repo: str
    title: str
    body: str
    labels: Optional[List[str]] = None


class MCPToolRequest(BaseModel):
    """Request model for calling MCP tools directly."""
    tool_name: str
    arguments: Dict[str, Any]


@router.get("/github/tools")
def get_github_tools():
    """Get list of available MCP GitHub tools."""
    return {
        "tools": github_agent.get_tools(),
        "available": github_agent.is_available()
    }


@router.post("/github/analyze")
def analyze_repository(request: GitHubRepositoryRequest):
    """
    Analyze a GitHub repository.
    Returns repository information, files, issues, and commits.
    """
    try:
        result = github_agent.analyze_repository(
            owner=request.owner,
            repo=request.repo,
            include_files=request.include_files,
            include_issues=request.include_issues,
            include_commits=request.include_commits
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/scan")
def scan_github_repository(request: GitHubScanRequest):
    """
    Prepare GitHub repository for scanning.
    Fetches repository data that can be used for scanning without cloning.
    """
    try:
        result = github_agent.scan_repository_for_scanning(
            owner=request.owner,
            repo=request.repo,
            scan_types=request.scan_types
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/issue")
def create_issue(request: CreateIssueRequest):
    """Create a GitHub issue."""
    try:
        github_service = MCPGitHubService()
        result = github_service.create_issue(
            owner=request.owner,
            repo=request.repo,
            title=request.title,
            body=request.body,
            labels=request.labels
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/mcp/tool")
def call_mcp_tool(request: MCPToolRequest):
    """
    Call an MCP GitHub tool directly.
    This provides direct access to all MCP GitHub tools.
    """
    try:
        github_service = MCPGitHubService()
        result = github_service.call_tool(
            tool_name=request.tool_name,
            arguments=request.arguments
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/github/repo/{owner}/{repo}/file")
def get_file(owner: str, repo: str, path: str, ref: Optional[str] = None):
    """Get file contents from GitHub repository."""
    try:
        github_service = MCPGitHubService()
        result = github_service.get_file_contents(
            owner=owner,
            repo=repo,
            path=path,
            ref=ref
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/github/repo/{owner}/{repo}/commits")
def get_commits(owner: str, repo: str, sha: Optional[str] = None, limit: int = 10):
    """Get commit history from GitHub repository."""
    try:
        github_service = MCPGitHubService()
        result = github_service.get_commits(
            owner=owner,
            repo=repo,
            sha=sha,
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
