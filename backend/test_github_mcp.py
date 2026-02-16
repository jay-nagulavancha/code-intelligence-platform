"""
Test script for GitHub MCP connection and capabilities.
Tests what the GitHub MCP service can access.
"""
import os
import sys
import json

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If dotenv not available, try to read .env manually
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from app.services.mcp_github_service import MCPGitHubService
from app.agents.github_agent import GitHubAgent
import requests

def test_github_mcp():
    """Test GitHub MCP service capabilities."""
    print("=" * 60)
    print("GitHub MCP Connection Test")
    print("=" * 60)
    
    # Initialize service
    github_service = MCPGitHubService()
    
    # Check availability
    print(f"\n1. Service Availability: {github_service.is_available()}")
    if not github_service.is_available():
        print("   ❌ GitHub token not found. Set GITHUB_TOKEN environment variable.")
        return
    
    print(f"   ✅ GitHub service is available")
    print(f"   Token: {github_service.github_token[:10]}...{github_service.github_token[-4:]}")
    
    # Get available tools
    print(f"\n2. Available MCP Tools:")
    tools = github_service.get_tools()
    print(f"   Total tools: {len(tools)}")
    for i, tool in enumerate(tools, 1):
        print(f"   {i}. {tool['name']}: {tool['description']}")
    
    # Test with a public repository (octocat/Hello-World)
    test_owner = "octocat"
    test_repo = "Hello-World"
    
    print(f"\n3. Testing Repository Access:")
    print(f"   Repository: {test_owner}/{test_repo}")
    
    try:
        # Test 1: Get repository info
        print(f"\n   Test 1: Get Repository Information")
        repo_info = github_service.get_repository(test_owner, test_repo)
        print(f"   ✅ Success!")
        print(f"      Name: {repo_info.get('name')}")
        print(f"      Full Name: {repo_info.get('full_name')}")
        print(f"      Description: {repo_info.get('description', 'N/A')}")
        print(f"      Language: {repo_info.get('language', 'N/A')}")
        print(f"      Stars: {repo_info.get('stargazers_count', 0)}")
        print(f"      Forks: {repo_info.get('forks_count', 0)}")
        print(f"      Default Branch: {repo_info.get('default_branch', 'N/A')}")
        print(f"      URL: {repo_info.get('html_url')}")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    try:
        # Test 2: List files
        print(f"\n   Test 2: List Repository Files")
        files = github_service.list_files(test_owner, test_repo)
        print(f"   ✅ Success!")
        print(f"      Found {len(files.get('items', []))} items")
        for item in files.get('items', [])[:5]:
            print(f"      - {item['name']} ({item['type']})")
        if len(files.get('items', [])) > 5:
            print(f"      ... and {len(files.get('items', [])) - 5} more")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    try:
        # Test 3: Get file contents
        print(f"\n   Test 3: Get File Contents (README.md)")
        file_content = github_service.get_file_contents(test_owner, test_repo, "README.md")
        print(f"   ✅ Success!")
        print(f"      File: {file_content.get('path')}")
        print(f"      Size: {file_content.get('size')} bytes")
        content_preview = file_content.get('content', '')[:200]
        print(f"      Content preview: {content_preview}...")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    try:
        # Test 4: Get commits
        print(f"\n   Test 4: Get Commit History")
        commits = github_service.get_commits(test_owner, test_repo, limit=5)
        print(f"   ✅ Success!")
        print(f"      Found {len(commits.get('commits', []))} commits")
        for commit in commits.get('commits', [])[:3]:
            print(f"      - {commit['sha'][:7]}: {commit['message'][:50]}...")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    try:
        # Test 5: Get issues
        print(f"\n   Test 5: Get Issues")
        issues = github_service.get_issues(test_owner, test_repo, limit=5)
        print(f"   ✅ Success!")
        print(f"      Found {len(issues.get('issues', []))} issues")
        for issue in issues.get('issues', [])[:3]:
            print(f"      - #{issue['number']}: {issue['title'][:50]}...")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    try:
        # Test 6: Get pull requests
        print(f"\n   Test 6: Get Pull Requests")
        prs = github_service.get_pull_requests(test_owner, test_repo, limit=5)
        print(f"   ✅ Success!")
        print(f"      Found {len(prs.get('pull_requests', []))} pull requests")
        for pr in prs.get('pull_requests', [])[:3]:
            print(f"      - #{pr['number']}: {pr['title'][:50]}...")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    # Test GitHub Agent
    print(f"\n4. Testing GitHub Agent:")
    github_agent = GitHubAgent()
    
    try:
        print(f"\n   Test: Analyze Repository")
        analysis = github_agent.analyze_repository(
            owner=test_owner,
            repo=test_repo,
            include_files=True,
            include_issues=True,
            include_commits=True
        )
        print(f"   ✅ Success!")
        print(f"      Repository analyzed successfully")
        if 'analysis' in analysis:
            repo_data = analysis.get('analysis', {}).get('repository', {})
            print(f"      Name: {repo_data.get('name')}")
            print(f"      Stars: {repo_data.get('stars', 0)}")
            print(f"      Files: {len(analysis.get('analysis', {}).get('files', {}).get('items', []))}")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    # Test MCP tool calling
    print(f"\n5. Testing MCP Tool Calls:")
    try:
        print(f"\n   Test: Call MCP Tool Directly")
        result = github_service.call_tool(
            tool_name="github_get_repository",
            arguments={"owner": test_owner, "repo": test_repo}
        )
        if "error" in result:
            print(f"   ❌ Error: {result['error']}")
        else:
            print(f"   ✅ Success! Tool call worked")
            print(f"      Repository: {result.get('full_name')}")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
    
    # Test with your own repository (if token has access)
    print(f"\n6. Testing Token Permissions:")
    try:
        # Try to get authenticated user info
        response = requests.get(
            f"{github_service.base_url}/user",
            headers=github_service.headers,
            timeout=10
        )
        if response.status_code == 200:
            user_info = response.json()
            print(f"   ✅ Token is valid")
            print(f"      Authenticated as: {user_info.get('login')}")
            print(f"      Name: {user_info.get('name', 'N/A')}")
            print(f"      Public Repos: {user_info.get('public_repos', 0)}")
            
            # Try to list user's repositories
            repos_response = requests.get(
                f"{github_service.base_url}/user/repos",
                headers=github_service.headers,
                params={"per_page": 5},
                timeout=10
            )
            if repos_response.status_code == 200:
                repos = repos_response.json()
                print(f"      Accessible Repositories: {len(repos)} (showing first 5)")
                for repo in repos[:3]:
                    print(f"         - {repo['full_name']} ({repo.get('private', False) and 'private' or 'public'})")
        else:
            print(f"   ⚠️  Token may have limited permissions: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Failed to check permissions: {str(e)}")
    
    print(f"\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_github_mcp()
