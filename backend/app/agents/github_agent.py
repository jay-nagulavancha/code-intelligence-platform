"""
GitHub Analyzer - Uses MCP GitHub Service to interact with GitHub repositories.
Can fetch repository data, read files, create issues, and more.
"""
from typing import List, Dict, Optional, Any
from app.services.mcp_github_service import MCPGitHubService


class GitHubAnalyzer:
    """
    Analyzer that interacts with GitHub using MCP protocol.
    Provides GitHub operations as tools for the Orchestrator Agent.
    """

    def __init__(self, github_service: Optional[MCPGitHubService] = None):
        """
        Initialize GitHub Analyzer.
        
        Args:
            github_service: MCP GitHub service instance
        """
        self.github_service = github_service or MCPGitHubService()

    def is_available(self) -> bool:
        """Check if GitHub agent is available."""
        return self.github_service.is_available()

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get available MCP tools for GitHub interactions."""
        return self.github_service.get_tools()

    def analyze_repository(
        self, 
        owner: str, 
        repo: str,
        include_files: bool = False,
        include_issues: bool = False,
        include_commits: bool = False
    ) -> Dict[str, Any]:
        """
        Comprehensive repository analysis using GitHub API.
        
        Args:
            owner: Repository owner
            repo: Repository name
            include_files: Whether to include file listing
            include_issues: Whether to include issues
            include_commits: Whether to include recent commits
        
        Returns:
            Repository analysis data
        """
        if not self.is_available():
            return {
                "error": "GitHub agent not available. Set GITHUB_TOKEN environment variable."
            }

        result = {
            "owner": owner,
            "repo": repo,
            "analysis": {}
        }

        # Get basic repository info
        try:
            repo_info = self.github_service.get_repository(owner, repo)
            result["analysis"]["repository"] = {
                "name": repo_info["name"],
                "full_name": repo_info["full_name"],
                "description": repo_info.get("description"),
                "language": repo_info.get("language"),
                "stars": repo_info.get("stargazers_count", 0),
                "forks": repo_info.get("forks_count", 0),
                "open_issues": repo_info.get("open_issues_count", 0),
                "default_branch": repo_info.get("default_branch", "main"),
                "created_at": repo_info.get("created_at"),
                "updated_at": repo_info.get("updated_at"),
                "url": repo_info.get("html_url")
            }
        except Exception as e:
            result["analysis"]["repository"] = {"error": str(e)}

        # Get file structure
        if include_files:
            try:
                files = self.github_service.list_files(owner, repo)
                result["analysis"]["files"] = files
            except Exception as e:
                result["analysis"]["files"] = {"error": str(e)}

        # Get recent issues
        if include_issues:
            try:
                issues = self.github_service.get_issues(owner, repo, limit=5)
                result["analysis"]["recent_issues"] = issues
            except Exception as e:
                result["analysis"]["recent_issues"] = {"error": str(e)}

        # Get recent commits
        if include_commits:
            try:
                commits = self.github_service.get_commits(owner, repo, limit=10)
                result["analysis"]["recent_commits"] = commits
            except Exception as e:
                result["analysis"]["recent_commits"] = {"error": str(e)}

        return result

    def scan_repository_for_scanning(
        self, 
        owner: str, 
        repo: str,
        scan_types: List[str]
    ) -> Dict[str, Any]:
        """
        Prepare repository data for scanning by fetching relevant information.
        This can be used to scan a GitHub repository without cloning it.
        
        Args:
            owner: Repository owner
            repo: Repository name
            scan_types: List of scan types to prepare for
        
        Returns:
            Repository data ready for scanning
        """
        result = {
            "owner": owner,
            "repo": repo,
            "scan_types": scan_types,
            "data": {}
        }

        # Get repository info
        try:
            repo_info = self.github_service.get_repository(owner, repo)
            result["data"]["repository"] = repo_info
            default_branch = repo_info.get("default_branch", "main")
        except Exception as e:
            return {"error": f"Failed to get repository info: {str(e)}"}

        # For security scans, get Python files
        if "security" in scan_types:
            try:
                # Try to find requirements.txt or similar
                try:
                    requirements = self.github_service.get_file_contents(
                        owner, repo, "requirements.txt", ref=default_branch
                    )
                    result["data"]["requirements"] = requirements
                except:
                    pass  # requirements.txt might not exist
            except Exception as e:
                result["data"]["security_files"] = {"error": str(e)}

        # For OSS scans, get dependency files
        if "oss" in scan_types:
            dependency_files = ["requirements.txt", "package.json", "Pipfile", "poetry.lock"]
            for dep_file in dependency_files:
                try:
                    content = self.github_service.get_file_contents(
                        owner, repo, dep_file, ref=default_branch
                    )
                    result["data"][dep_file] = content
                    break  # Use first found
                except:
                    continue

        # For change analysis, get recent commits
        if "change" in scan_types:
            try:
                commits = self.github_service.get_commits(owner, repo, limit=20)
                result["data"]["recent_commits"] = commits
            except Exception as e:
                result["data"]["commits"] = {"error": str(e)}

        return result

    def create_scan_issue(
        self,
        owner: str,
        repo: str,
        scan_results: Dict[str, Any],
        issue_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a GitHub issue from scan results.
        
        Args:
            owner: Repository owner
            repo: Repository name
            scan_results: Results from scan
            issue_title: Custom issue title (optional)
        
        Returns:
            Created issue information
        """
        if not self.is_available():
            return {"error": "GitHub agent not available"}

        # Generate issue body from scan results
        body_parts = ["## Scan Results\n\n"]
        
        if "report" in scan_results:
            report = scan_results["report"]
            if "summary" in report:
                summary = report["summary"]
                body_parts.append(f"**Total Issues:** {summary.get('total_issues', 0)}\n\n")
            
            if "critical_issues" in report:
                body_parts.append("### Critical Issues\n\n")
                for issue in report["critical_issues"][:5]:
                    body_parts.append(f"- {issue.get('message', 'Unknown issue')}\n")
                body_parts.append("\n")
            
            if "recommendations" in report:
                body_parts.append("### Recommendations\n\n")
                for rec in report["recommendations"][:5]:
                    body_parts.append(f"- {rec.get('title', 'Recommendation')}\n")
                body_parts.append("\n")

        body = "".join(body_parts)
        title = issue_title or f"Code Intelligence Scan Results - {scan_results.get('scan_id', 'Unknown')}"

        try:
            issue = self.github_service.create_issue(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                labels=["code-intelligence", "scan-results"]
            )
            return issue
        except Exception as e:
            return {"error": str(e)}

