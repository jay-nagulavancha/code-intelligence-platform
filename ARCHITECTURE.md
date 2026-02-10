# Multi-Agent Code Intelligence Platform - Architecture Diagram

## Visual Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Multi-Agent Code Intelligence Platform                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   FastAPI       │
│ /api/scan       │
│ /api/github     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐         ┌──────────────────┐
│  ScanService    │────────▶│   RAG Service    │
│                 │         │  (FAISS/Qdrant)  │
└────────┬────────┘         └──────────────────┘
         │
         │ Query historical context
         │ Store results
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│           Orchestrator Agent (LLM-Powered)               │
│  • Decides which agents to run                          │
│  • Combines outputs                                     │
│  • Generates recommendations                            │
│  • Uses MCP tools for GitHub interactions               │
└────────┬────────────────────────────────────────────────┘
         │
         ├──────────┬──────────┬──────────┬──────────┬──────────┐
         │          │          │          │          │          │
         ▼          ▼          ▼          ▼          ▼          ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Security    │ │    OSS      │ │   Change     │ │ Deprecation  │ │   GitHub     │
│   Agent      │ │   Agent     │ │   Agent     │ │    Agent     │ │   Agent      │
│              │ │             │ │             │ │              │ │  (MCP)       │
│  (Bandit)    │ │(pip-licenses)│ │ (git diff)  │ │ (AST rules)  │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────┬───────┘
         │                 │                 │                 │            │
         └─────────────────┴─────────────────┴─────────────────┘            │
                              │                                              │
                              ▼                                              ▼
                    ┌──────────────────┐                        ┌──────────────────┐
                    │   LLM Service   │                        │  MCP GitHub      │
                    │  (Ollama/OpenAI)│                        │   Service        │
                    │                  │                        │                  │
                    │ • Release notes  │                        │ • Repository API │
                    │ • Fix suggestions│                        │ • File operations│
                    │ • Summaries      │                        │ • Issue creation │
                    └──────────────────┘                        │ • PR management  │
                                                                 └──────────────────┘
```

## Component Details

### 1. API Layer (FastAPI)
- **Endpoints**: 
  - `/api/scan` - Code scanning operations
  - `/api/github` - GitHub repository interactions
- Receives scan requests with:
  - Repository path or GitHub owner/repo
  - Scan types (security, oss, change, deprecation)
  - Project context
  - RAG storage flag

### 2. ScanService
- **Purpose**: Main orchestration service
- **Responsibilities**:
  - Coordinates Orchestrator Agent
  - Integrates with RAG for historical context
  - Enhances results with LLM
  - Stores results in RAG
  - Supports both local and GitHub repositories

### 3. RAG Service
- **Purpose**: Retrieval Augmented Generation
- **Vector DBs**: FAISS (default) or Qdrant
- **Functions**:
  - Stores historical scans, issues, code snippets
  - Semantic search for similar past scans
  - Provides context for informed reasoning

### 4. Orchestrator Agent
- **Purpose**: LLM-powered intelligent agent selection
- **Capabilities**:
  - Analyzes scan request and project context
  - Decides which agents to execute
  - Combines agent outputs into coherent reports
  - Generates actionable recommendations
  - Can use MCP tools for GitHub interactions

### 5. Tool-Calling Agents

#### Security Agent
- **Tools**: 
  - Python: Bandit (static analysis)
  - Java: SpotBugs (static analysis)
- **Features**:
  - Auto-detects project language
  - Multi-language support
  - Standardized output format
- **Output**: Security vulnerabilities with severity, confidence, CWE, file, line

#### OSS Agent
- **Tools**: 
  - Python: pip-licenses (license information)
  - Java: OWASP Dependency-Check (licenses + vulnerability scanning)
- **Features**:
  - Auto-detects project language
  - Scans Maven and Gradle dependencies
  - Checks for known CVEs in JAR files
  - Provides CVSS scores and severity levels
- **Output**: Dependencies with licenses and known vulnerabilities (CVE, CVSS, severity)

#### Change Agent
- **Tool**: git diff
- **Output**: Code changes with file paths, line numbers, change types

#### Deprecation Agent
- **Tool**: AST analysis
- **Output**: Deprecated code patterns with locations

#### GitHub Agent (NEW)
- **Protocol**: Model Context Protocol (MCP)
- **Service**: MCP GitHub Service
- **Capabilities**:
  - Repository analysis and metadata
  - File content retrieval
  - Commit history access
  - Issue creation and management
  - Pull request information
  - Diff generation
- **Use Cases**:
  - Scan GitHub repositories without cloning
  - Create issues from scan results
  - Analyze repository structure
  - Fetch code for analysis

### 6. LLM Service
- **Providers**: Ollama (default), OpenAI, Hugging Face
- **Functions**:
  - Generate human-readable release notes
  - Suggest fixes for vulnerabilities
  - Summarize deprecation issues
  - Create comprehensive reports

### 7. MCP GitHub Service (NEW)
- **Protocol**: Model Context Protocol
- **Purpose**: Standardized GitHub API interactions
- **Tools Available**:
  1. `github_get_repository` - Get repository info
  2. `github_get_file_contents` - Read files
  3. `github_list_files` - List directory contents
  4. `github_get_commits` - Get commit history
  5. `github_get_issues` - List issues
  6. `github_create_issue` - Create issues
  7. `github_get_pull_requests` - Get PRs
  8. `github_get_diff` - Get diffs between commits

## Data Flow

1. **Request** → API receives scan request (local path or GitHub repo)
2. **RAG Query** → ScanService queries historical context
3. **GitHub Check** → If GitHub repo, fetch data via MCP GitHub Service
4. **Orchestration** → Orchestrator Agent decides which agents to run
5. **Execution** → Selected agents execute in parallel
6. **LLM Enhancement** → LLM generates release notes, suggestions, summaries
7. **GitHub Integration** → Optionally create issues or PRs from results
8. **RAG Storage** → Results stored for future queries
9. **Response** → Comprehensive report returned

## Technology Stack

- **API**: FastAPI
- **LLM**: Ollama (dev) / OpenAI (prod)
- **Vector DB**: FAISS / Qdrant
- **Agents**: Bandit, pip-licenses, git, AST
- **GitHub Integration**: MCP (Model Context Protocol)
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2)

## Key Features

### Multi-Agent Orchestration
- LLM-powered agent selection
- Parallel agent execution
- Intelligent output combination

### GitHub Integration (NEW)
- Scan repositories without cloning
- Direct file access via GitHub API
- Automated issue creation from scan results
- Repository analysis and metadata

### RAG-Enhanced Intelligence
- Historical context retrieval
- Similar scan pattern matching
- Informed decision-making

### LLM-Powered Reports
- Human-readable release notes
- Vulnerability fix suggestions
- Deprecation summaries
- Actionable recommendations

## Setup Requirements

1. **LLM**: Ollama (default) or OpenAI API key
2. **Vector DB**: FAISS (auto-installed) or Qdrant
3. **GitHub**: Personal Access Token (for GitHub features)
4. **Tools**: Bandit, pip-licenses, git

See individual setup guides:
- `backend/LLM_SETUP.md` - LLM configuration
- `backend/MCP_GITHUB_SETUP.md` - GitHub integration setup
