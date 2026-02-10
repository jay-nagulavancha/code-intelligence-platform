# MCP GitHub Integration Setup

This project uses Model Context Protocol (MCP) to interact with GitHub repositories, enabling agents to fetch code, create issues, analyze repositories, and more.

## Overview

The MCP GitHub integration provides:
- **Repository Analysis** - Fetch repository metadata, files, commits, issues
- **File Operations** - Read file contents directly from GitHub
- **Issue Management** - Create and manage GitHub issues
- **Pull Request Access** - Get PR information and diffs
- **Code Scanning** - Prepare repositories for scanning without cloning

## Setup

### 1. Create GitHub Personal Access Token

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Select scopes:
   - `repo` - Full control of private repositories
   - `read:org` - Read org and team membership (if needed)
4. Copy the token

### 2. Configure Environment Variable

Add to your `.env` file or export:

```bash
GITHUB_TOKEN=your_github_token_here
```

Or set as environment variable:

```bash
export GITHUB_TOKEN=your_github_token_here
```

### 3. Verify Setup

Check if GitHub integration is available:

```bash
curl http://localhost:8000/health
```

Should show `"github_available": true`

## API Endpoints

### Get Available Tools

```bash
GET /api/github/tools
```

Returns list of all available MCP GitHub tools.

### Analyze Repository

```bash
POST /api/github/analyze
Content-Type: application/json

{
  "owner": "octocat",
  "repo": "Hello-World",
  "include_files": true,
  "include_issues": true,
  "include_commits": true
}
```

### Scan Repository

```bash
POST /api/github/scan
Content-Type: application/json

{
  "owner": "octocat",
  "repo": "Hello-World",
  "scan_types": ["security", "oss", "change"]
}
```

### Get File Contents

```bash
GET /api/github/repo/{owner}/{repo}/file?path=README.md&ref=main
```

### Get Commits

```bash
GET /api/github/repo/{owner}/{repo}/commits?limit=10&sha=main
```

### Create Issue

```bash
POST /api/github/issue
Content-Type: application/json

{
  "owner": "octocat",
  "repo": "Hello-World",
  "title": "Security vulnerability found",
  "body": "Description of the issue...",
  "labels": ["security", "bug"]
}
```

### Call MCP Tool Directly

```bash
POST /api/github/mcp/tool
Content-Type: application/json

{
  "tool_name": "github_get_repository",
  "arguments": {
    "owner": "octocat",
    "repo": "Hello-World"
  }
}
```

## Available MCP Tools

### 1. `github_get_repository`
Get repository information.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name

### 2. `github_get_file_contents`
Get file contents from repository.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `path` (string, required): File path
- `ref` (string, optional): Branch/commit SHA

### 3. `github_list_files`
List files in a directory.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `path` (string, optional): Directory path (default: root)
- `ref` (string, optional): Branch/commit SHA

### 4. `github_get_commits`
Get commit history.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `sha` (string, optional): SHA or branch
- `path` (string, optional): Filter by file path
- `limit` (integer, optional): Number of commits (default: 10)

### 5. `github_get_issues`
Get repository issues.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `state` (string, optional): open, closed, or all (default: open)
- `limit` (integer, optional): Number of issues (default: 10)

### 6. `github_create_issue`
Create a new issue.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `title` (string, required): Issue title
- `body` (string, required): Issue body
- `labels` (array, optional): Issue labels

### 7. `github_get_pull_requests`
Get pull requests.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `state` (string, optional): open, closed, or all (default: open)
- `limit` (integer, optional): Number of PRs (default: 10)

### 8. `github_get_diff`
Get diff between two commits/branches.

**Arguments:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `base` (string, required): Base commit/branch
- `head` (string, required): Head commit/branch

## Usage Examples

### Python Example

```python
from app.services.mcp_github_service import MCPGitHubService

# Initialize service
github = MCPGitHubService()

# Get repository info
repo_info = github.get_repository("octocat", "Hello-World")
print(f"Repository: {repo_info['full_name']}")
print(f"Stars: {repo_info['stargazers_count']}")

# Get file contents
readme = github.get_file_contents("octocat", "Hello-World", "README.md")
print(readme["content"])

# Create issue from scan results
issue = github.create_issue(
    owner="octocat",
    repo="Hello-World",
    title="Security scan found vulnerabilities",
    body="Found 5 high-severity issues...",
    labels=["security", "automated"]
)
```

### Using GitHub Agent

```python
from app.agents.github_agent import GitHubAgent

agent = GitHubAgent()

# Analyze repository
analysis = agent.analyze_repository(
    owner="octocat",
    repo="Hello-World",
    include_files=True,
    include_issues=True,
    include_commits=True
)

# Prepare for scanning
scan_data = agent.scan_repository_for_scanning(
    owner="octocat",
    repo="Hello-World",
    scan_types=["security", "oss"]
)
```

## Integration with Orchestrator Agent

The GitHub Agent is integrated into the Orchestrator Agent, allowing LLM-powered decisions to use GitHub tools:

```python
from app.agents.orchestrator_agent import OrchestratorAgent

orchestrator = OrchestratorAgent()

# The orchestrator can now use GitHub tools when needed
# The LLM can decide to fetch repository info, create issues, etc.
```

## Rate Limiting

GitHub API has rate limits:
- **Authenticated requests**: 5,000 requests/hour
- **Unauthenticated requests**: 60 requests/hour

The service automatically uses authentication when `GITHUB_TOKEN` is set.

## Security Considerations

1. **Token Security**: Never commit tokens to version control
2. **Token Permissions**: Use minimal required scopes
3. **Token Rotation**: Rotate tokens regularly
4. **Private Repos**: Ensure token has access to private repositories if needed

## Troubleshooting

### "GitHub service not available"
- Check if `GITHUB_TOKEN` is set
- Verify token is valid and not expired
- Ensure token has required scopes

### "Not Found" errors
- Verify repository owner and name are correct
- Check if repository is private and token has access
- Ensure file paths are correct

### Rate limit errors
- Wait for rate limit to reset
- Use authenticated requests (set `GITHUB_TOKEN`)
- Implement rate limiting in your application

## Next Steps

- Integrate with scan results to auto-create GitHub issues
- Use GitHub webhooks for automated scanning
- Implement PR comment automation
- Add support for GitHub Actions integration
