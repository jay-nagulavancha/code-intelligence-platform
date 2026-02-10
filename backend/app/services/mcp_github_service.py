"""
MCP GitHub Service - Model Context Protocol integration for GitHub interactions.
Enables agents to interact with GitHub repositories, issues, PRs, and more.
"""
import os
import json
import requests
from typing import Dict, Any, List, Optional
from urllib.parse import quote


class MCPGitHubService:
    """
    MCP-compatible GitHub service that provides tools for GitHub interactions.
    Follows Model Context Protocol for standardized LLM-tool communication.
    """

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize MCP GitHub Service.
        
        Args:
            github_token: GitHub personal access token (or from env GITHUB_TOKEN)
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Code-Intelligence-Platform"
        }
        
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"

    def is_available(self) -> bool:
        """Check if GitHub service is available (has token)."""
        return self.github_token is not None

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        Return list of available MCP tools for GitHub interactions.
        This follows the MCP tool definition format.
        """
        return [
            {
                "name": "github_get_repository",
                "description": "Get repository information from GitHub",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"}
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_get_file_contents",
                "description": "Get file contents from a GitHub repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "path": {"type": "string", "description": "File path in repository"},
                        "ref": {"type": "string", "description": "Branch/commit SHA (optional)"}
                    },
                    "required": ["owner", "repo", "path"]
                }
            },
            {
                "name": "github_list_files",
                "description": "List files in a GitHub repository directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "path": {"type": "string", "description": "Directory path (default: root)"},
                        "ref": {"type": "string", "description": "Branch/commit SHA (optional)"}
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_get_commits",
                "description": "Get commit history from a GitHub repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "sha": {"type": "string", "description": "SHA or branch (optional)"},
                        "path": {"type": "string", "description": "Filter by file path (optional)"},
                        "limit": {"type": "integer", "description": "Number of commits (default: 10)"}
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_get_issues",
                "description": "Get issues from a GitHub repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "state": {"type": "string", "description": "open, closed, or all (default: open)"},
                        "limit": {"type": "integer", "description": "Number of issues (default: 10)"}
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_create_issue",
                "description": "Create a new issue in a GitHub repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "title": {"type": "string", "description": "Issue title"},
                        "body": {"type": "string", "description": "Issue body/description"},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "Issue labels"}
                    },
                    "required": ["owner", "repo", "title", "body"]
                }
            },
            {
                "name": "github_get_pull_requests",
                "description": "Get pull requests from a GitHub repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "state": {"type": "string", "description": "open, closed, or all (default: open)"},
                        "limit": {"type": "integer", "description": "Number of PRs (default: 10)"}
                    },
                    "required": ["owner", "repo"]
                }
            },
            {
                "name": "github_get_diff",
                "description": "Get diff between two commits or branches",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "base": {"type": "string", "description": "Base commit/branch"},
                        "head": {"type": "string", "description": "Head commit/branch"}
                    },
                    "required": ["owner", "repo", "base", "head"]
                }
            }
        ]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool by name with arguments.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
        
        Returns:
            Tool execution result
        """
        if not self.is_available():
            return {
                "error": "GitHub service not available. Set GITHUB_TOKEN environment variable."
            }

        tool_map = {
            "github_get_repository": self.get_repository,
            "github_get_file_contents": self.get_file_contents,
            "github_list_files": self.list_files,
            "github_get_commits": self.get_commits,
            "github_get_issues": self.get_issues,
            "github_create_issue": self.create_issue,
            "github_get_pull_requests": self.get_pull_requests,
            "github_get_diff": self.get_diff
        }

        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return tool_map[tool_name](**arguments)
        except Exception as e:
            return {"error": str(e)}

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository information."""
        url = f"{self.base_url}/repos/{owner}/{repo}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_file_contents(self, owner: str, repo: str, path: str, ref: Optional[str] = None) -> Dict[str, Any]:
        """Get file contents from repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{quote(path, safe='')}"
        params = {}
        if ref:
            params["ref"] = ref
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Decode base64 content if it's a file
        if data.get("type") == "file" and "content" in data:
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            return {
                "path": data["path"],
                "sha": data["sha"],
                "size": data["size"],
                "content": content,
                "encoding": "utf-8"
            }
        
        return data

    def list_files(self, owner: str, repo: str, path: str = "", ref: Optional[str] = None) -> Dict[str, Any]:
        """List files in a directory."""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents"
        if path:
            url += f"/{quote(path, safe='')}"
        
        params = {}
        if ref:
            params["ref"] = ref
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        items = response.json()
        
        return {
            "path": path or "/",
            "items": [
                {
                    "name": item["name"],
                    "type": item["type"],
                    "path": item["path"],
                    "size": item.get("size", 0),
                    "sha": item["sha"]
                }
                for item in items
            ]
        }

    def get_commits(self, owner: str, repo: str, sha: Optional[str] = None, 
                   path: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Get commit history."""
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        params = {"per_page": min(limit, 100)}
        if sha:
            params["sha"] = sha
        if path:
            params["path"] = path
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        commits = response.json()
        
        return {
            "commits": [
                {
                    "sha": commit["sha"],
                    "message": commit["commit"]["message"],
                    "author": commit["commit"]["author"]["name"],
                    "date": commit["commit"]["author"]["date"],
                    "url": commit["html_url"]
                }
                for commit in commits[:limit]
            ]
        }

    def get_issues(self, owner: str, repo: str, state: str = "open", limit: int = 10) -> Dict[str, Any]:
        """Get repository issues."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        params = {
            "state": state,
            "per_page": min(limit, 100)
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        issues = response.json()
        
        return {
            "issues": [
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue["body"],
                    "state": issue["state"],
                    "labels": [label["name"] for label in issue["labels"]],
                    "created_at": issue["created_at"],
                    "url": issue["html_url"]
                }
                for issue in issues[:limit]
            ]
        }

    def create_issue(self, owner: str, repo: str, title: str, body: str, 
                    labels: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new issue."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        payload = {
            "title": title,
            "body": body
        }
        if labels:
            payload["labels"] = labels
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        issue = response.json()
        
        return {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "url": issue["html_url"]
        }

    def get_pull_requests(self, owner: str, repo: str, state: str = "open", 
                         limit: int = 10) -> Dict[str, Any]:
        """Get pull requests."""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        params = {
            "state": state,
            "per_page": min(limit, 100)
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        prs = response.json()
        
        return {
            "pull_requests": [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "body": pr["body"],
                    "state": pr["state"],
                    "head": pr["head"]["ref"],
                    "base": pr["base"]["ref"],
                    "created_at": pr["created_at"],
                    "url": pr["html_url"]
                }
                for pr in prs[:limit]
            ]
        }

    def get_diff(self, owner: str, repo: str, base: str, head: str) -> Dict[str, Any]:
        """Get diff between two commits/branches."""
        url = f"{self.base_url}/repos/{owner}/{repo}/compare/{base}...{head}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        comparison = response.json()
        
        return {
            "base": base,
            "head": head,
            "ahead_by": comparison["ahead_by"],
            "behind_by": comparison["behind_by"],
            "total_commits": comparison["total_commits"],
            "files": [
                {
                    "filename": file["filename"],
                    "status": file["status"],
                    "additions": file["additions"],
                    "deletions": file["deletions"],
                    "changes": file["changes"],
                    "patch": file.get("patch", "")
                }
                for file in comparison["files"]
            ]
        }
