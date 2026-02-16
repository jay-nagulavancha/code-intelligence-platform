# Multi-Agent Code Intelligence Platform - Architecture

## Visual Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Multi-Agent Code Intelligence Platform                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐      CLI: scan_github_repo.py
│   FastAPI       │      (--no-issues, --no-rag, --scan-types)
│ /api/scan       │
│ /api/github     │
└────────┬────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────┐
│  ScanService  (full pipeline)                                     │
│                                                                   │
│  scan_github_repo()                                               │
│    1. Fetch repo info (GitHub API)                                │
│    2. Clone repository (--depth 1)                                │
│    3. Detect language ──▶ ProjectBuilder: auto-build Java         │
│    4. Run agents (Orchestrator) ──▶ LLM enhance ──▶ RAG store    │
│    5. Create GitHub Issues (critical/high findings)               │
│    6. Cleanup temp clone                                          │
│                                                                   │
│  run_scan()                                                       │
│    1. RAG historical context query                                │
│    2. Orchestrator: decide → run agents → combine (LLM)           │
│    3. LLM enhancement (fix suggestions, summaries, release notes) │
│    4. RAG storage                                                 │
└────────┬──────────────────────────────────────────────────────────┘
         │
         ├──────────┬──────────┬──────────┬──────────┬──────────┐
         ▼          ▼          ▼          ▼          ▼          ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Security    │ │    OSS      │ │   Change     │ │ Deprecation  │ │   GitHub     │
│   Agent      │ │   Agent     │ │   Agent      │ │    Agent     │ │   Agent      │
│              │ │             │ │              │ │              │ │  (MCP)       │
│ Bandit  (Py) │ │pip-licenses │ │  (git diff)  │ │ (AST rules)  │ │              │
│ SpotBugs(Ja) │ │OWASP DepChk │ │              │ │              │ │              │
│              │ │             │ │              │ │              │ │              │
│ Auto-build ✓ │ │ Auto-build ✓│ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────┬───────┘
         │                 │                 │                 │            │
         └─────────────────┴─────────────────┴─────────────────┘            │
                              │                                              │
              ┌───────────────┼───────────────┐                              │
              ▼               ▼               ▼                              ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   LLM Service   │ │   RAG Service    │ │ ProjectBuilder   │ │  MCP GitHub      │
│  (Ollama/OpenAI)│ │ (FAISS/Qdrant)  │ │ (Maven/Gradle)   │ │   Service        │
│                  │ │                  │ │                  │ │                  │
│ • Release notes  │ │ • Store scans   │ │ • Detect build   │ │ • Repository API │
│ • Fix suggestions│ │ • Query history │ │ • Detect Java ver │ │ • File operations│
│ • Summaries      │ │ • Pattern match │ │ • Resolve JDK     │ │ • Issue creation │
│ • Combine report │ │ • Embeddings    │ │ • Run mvn/gradle  │ │ • PR management  │
└──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘
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

### 2. ScanService (Full Pipeline)
- **Purpose**: End-to-end scan orchestration
- **Methods**:
  - `run_scan()` — local repository scan with RAG + LLM
  - `scan_github_repo()` — full GitHub pipeline (clone → build → scan → LLM → RAG → issues)
- **Responsibilities**:
  - Clones GitHub repositories (shallow clone `--depth 1`)
  - Detects language and triggers ProjectBuilder for Java
  - Coordinates Orchestrator Agent for agent execution
  - Queries RAG for historical context before scanning
  - Enhances results with LLM (fix suggestions, summaries, release notes)
  - Stores results in RAG for future scans
  - Auto-creates GitHub Issues for critical/high severity findings

### 3. RAG Service
- **Purpose**: Retrieval Augmented Generation for historical context
- **Vector DBs**: FAISS (default, in-memory) or Qdrant (persistent, scalable)
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- **Functions**:
  - `store_scan()` — persist scan results as vector embeddings
  - `query_similar_scans()` — semantic search for similar past scans
  - `get_historical_context()` — retrieve patterns and trends for current scan

### 4. Orchestrator Agent
- **Purpose**: LLM-powered intelligent agent selection and report combination
- **Capabilities**:
  - Analyzes scan request and project context
  - Uses LLM to decide which agents to execute (falls back to direct mapping)
  - Runs selected agents and collects outputs
  - Uses LLM to combine outputs into coherent report with recommendations
  - Generates actionable next steps

### 5. Tool-Calling Agents

#### Security Agent
- **Tools**: 
  - Python: Bandit (static analysis)
  - Java: SpotBugs (static analysis)
- **Features**:
  - Auto-detects project language via `ProjectDetector`
  - **Auto-builds Java projects** via `ProjectBuilder` when compiled classes are missing
  - Multi-language support (Python + Java)
  - Standardized output format
- **Output**: Security vulnerabilities with severity, confidence, CWE, file, line

#### OSS Agent
- **Tools**: 
  - Python: pip-licenses (license information)
  - Java: OWASP Dependency-Check (licenses + vulnerability scanning)
- **Features**:
  - Auto-detects project language via `ProjectDetector`
  - **Auto-builds Java projects** via `ProjectBuilder` before dependency scanning
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

#### GitHub Agent
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
  - Scan GitHub repositories via `ScanService.scan_github_repo()`
  - Auto-create issues from scan results (critical/high findings)
  - Analyze repository structure
  - Fetch code for analysis

### 6. LLM Service
- **Providers**: Ollama (default for dev), OpenAI (for prod), Hugging Face
- **Functions**:
  - Generate human-readable release notes from change analysis
  - Suggest fixes for security vulnerabilities (per-issue recommendations)
  - Summarize deprecation issues with migration paths
  - Combine agent outputs into comprehensive reports with recommendations
  - Graceful fallback when LLM is unavailable (raw structured data returned)

### 7. ProjectBuilder (Auto-Build)
- **Purpose**: Automatically build Java projects before scanning
- **Capabilities**:
  - `detect_build_system()` — detects Maven (`pom.xml`), Gradle (`build.gradle`), or Gradle wrapper (`gradlew`)
  - `_detect_required_java_version()` — reads `java.version`, `maven.compiler.release`, etc. from `pom.xml` properties; reads `sourceCompatibility` from `build.gradle`
  - `_resolve_java_home()` — uses `/usr/libexec/java_home -v <version>` (macOS) to find the correct JDK; falls back to scanning `/Library/Java/JavaVirtualMachines/`
  - `build()` — runs `mvn compile -q -DskipTests` or `gradlew compileJava -q -x test` with the correct `JAVA_HOME`
  - Prefers Maven/Gradle wrappers (`mvnw`, `gradlew`) when present
  - 10-minute build timeout with error diagnostics

### 8. ProjectDetector
- **Purpose**: Detect programming languages and build tools in a repository
- **Uses**: File/extension indicator patterns (`pom.xml` → Java, `requirements.txt` → Python, etc.)
- **Methods**: `detect_languages()`, `get_primary_language()`, `get_project_info()`

### 9. MCP GitHub Service
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

1. **Request** → API receives scan request (local path or GitHub repo) or CLI invokes `scan_github_repo.py`
2. **GitHub Fetch** → If GitHub repo, fetch metadata via MCP GitHub Service
3. **Clone** → Shallow clone repository to temp directory (`git clone --depth 1`)
4. **Detect & Build** → `ProjectDetector` identifies language; `ProjectBuilder` auto-builds Java projects (resolves correct JDK version)
5. **RAG Query** → `ScanService` queries RAG for historical context from similar past scans
6. **Orchestration** → `OrchestratorAgent` uses LLM to decide which agents to run, then executes them
7. **LLM Enhancement** → LLM generates vulnerability fix suggestions, release notes, deprecation summaries
8. **GitHub Issues** → Auto-create GitHub Issues for critical/high findings (formatted markdown with severity table, file locations, AI-generated fix suggestions)
9. **RAG Storage** → Results stored as vector embeddings for future queries
10. **Response** → Comprehensive report returned (JSON + console output)
11. **Cleanup** → Remove temporary clone directory

## Technology Stack

- **API**: FastAPI
- **CLI**: `scan_github_repo.py` (argparse)
- **LLM**: Ollama (dev) / OpenAI (prod) / Hugging Face
- **Vector DB**: FAISS (default) / Qdrant (scalable)
- **Embeddings**: sentence-transformers (`all-MiniLM-L6-v2`)
- **SAST**: Bandit (Python), SpotBugs (Java)
- **SCA**: pip-licenses (Python), OWASP Dependency-Check (Java)
- **Build**: Maven, Gradle (auto-detected, auto-invoked)
- **GitHub Integration**: MCP (Model Context Protocol) + GitHub REST API
- **Containerization**: Docker + Docker Compose

## Key Features

### Multi-Agent Orchestration
- LLM-powered agent selection
- Parallel agent execution
- Intelligent output combination with recommendations

### Auto-Build for Java Projects
- Detects required Java version from `pom.xml` / `build.gradle`
- Resolves correct JDK automatically (macOS `java_home`)
- Builds with Maven or Gradle wrapper before scanning
- Graceful fallback if build fails

### GitHub Integration
- Full pipeline: clone → build → scan → issues
- Auto-create GitHub Issues for critical/high findings
- Formatted markdown with severity tables, file locations, AI fix suggestions
- Use `--no-issues` flag to disable

### RAG-Enhanced Intelligence
- Historical context retrieval from past scans
- Similar scan pattern matching
- Trend analysis across scans
- Use `--no-rag` flag to disable

### LLM-Powered Reports
- Vulnerability fix suggestions (per-issue)
- Human-readable release notes
- Deprecation summaries with migration paths
- Actionable recommendations and next steps
- Graceful fallback when LLM is unavailable

## CLI Usage

```bash
# Full pipeline (scan + LLM + RAG + GitHub Issues)
python scan_github_repo.py <owner> <repo>

# Skip GitHub issue creation
python scan_github_repo.py <owner> <repo> --no-issues

# Skip RAG storage
python scan_github_repo.py <owner> <repo> --no-rag

# Custom scan types
python scan_github_repo.py <owner> <repo> --scan-types security oss deprecation

# Example
python scan_github_repo.py jay-nagulavancha spring-boot-spring-security-jwt-authentication
```

## Setup Requirements

1. **Python 3.8+**
2. **LLM**: Ollama (default) or OpenAI API key
3. **Vector DB**: FAISS (`pip install faiss-cpu sentence-transformers`) or Qdrant
4. **GitHub**: Personal Access Token (for GitHub features)
5. **SAST Tools**: Bandit (`pip install bandit`), SpotBugs (`brew install spotbugs`)
6. **SCA Tools**: pip-licenses (`pip install pip-licenses`), OWASP Dependency-Check (`brew install dependency-check`)
7. **Build Tools** (for Java): Maven or Gradle + appropriate JDK

See individual setup guides:
- `backend/LLM_SETUP.md` - LLM configuration
- `backend/MCP_GITHUB_SETUP.md` - GitHub integration setup
- `backend/JAVA_SCANNING_SETUP.md` - Java security scanning with SpotBugs
- `backend/DEPENDENCY_SCANNING_SETUP.md` - Dependency vulnerability scanning with OWASP Dependency-Check
