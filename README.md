# Code Intelligence Platform

AI-powered, multi-agent code analysis platform with LLM orchestration, RAG integration, and GitHub support.

## 🚀 Features

### Orchestrator + Analyzer System
- **Orchestrator Agent**: LLM-powered intelligent agent selection and coordination
- **Security Analyzer**: Multi-language vulnerability scanning (Python: Bandit, Java: SpotBugs) with **auto-build**
- **OSS Analyzer**: Multi-language dependency scanning (Python: pip-licenses, Java: OWASP Dependency-Check) with **auto-build**
- **Change Analyzer**: Git diff analysis for code changes
- **Deprecation Analyzer**: AST-based deprecated code detection
- **GitHub Analyzer**: MCP-based GitHub repository interactions

### Auto-Build for Java Projects
- **ProjectBuilder**: Automatically detects and builds Maven/Gradle projects before scanning
- **Java Version Detection**: Reads `java.version` from `pom.xml` or `sourceCompatibility` from `build.gradle`
- **JDK Resolution**: Finds the correct JDK on macOS via `/usr/libexec/java_home`
- **Wrapper Support**: Prefers `mvnw`/`gradlew` wrappers when available

### LLM Integration
- **Multiple Providers**: Ollama (default), OpenAI, Hugging Face
- **Intelligent Orchestration**: LLM decides which agents to run
- **Report Generation**: Human-readable release notes, fix suggestions, summaries
- **Context-Aware**: Uses project context for better decisions

### RAG (Retrieval Augmented Generation)
- **Historical Context**: Stores and retrieves past scan results
- **Vector Database**: FAISS (default) or Qdrant support
- **Semantic Search**: Find similar past scans and patterns
- **Informed Reasoning**: Use historical data for better analysis

### GitHub Integration (MCP)
- **Repository Analysis**: Fetch metadata, files, commits, issues
- **File Operations**: Read files directly from GitHub without cloning
- **Auto-Issue Creation**: Automatically creates GitHub Issues for critical/high findings with formatted markdown
- **Pull Request Access**: Get PR information and diffs
- **Full Pipeline**: Clone → Build → Scan → LLM Enhance → RAG Store → Create Issues

## 📋 Quick Start

### Prerequisites

```bash
# Python 3.8+
python --version

# Install Ollama (for LLM)
brew install ollama  # macOS
# or visit https://ollama.com

# Start Ollama
ollama serve
ollama pull llama3.2:3b
```

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd code-intelligence-platform/backend

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GITHUB_TOKEN=your_github_token  # Optional, for GitHub features
export LLM_PROVIDER=ollama  # Optional, defaults to ollama
export OLLAMA_MODEL=llama3.2:3b  # Optional

# Run the server
uvicorn app.main:app --reload
```

### Basic Usage

#### Scan Local Repository

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "repoPath": "/path/to/repo",
    "scanTypes": ["security", "oss", "change"],
    "storeInRAG": true
  }'
```

#### Analyze GitHub Repository

```bash
curl -X POST http://localhost:8000/api/github/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "octocat",
    "repo": "Hello-World",
    "include_files": true,
    "include_issues": true,
    "include_commits": true
  }'
```

#### Scan GitHub Repository

```bash
curl -X POST http://localhost:8000/api/github/scan \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "octocat",
    "repo": "Hello-World",
    "scanTypes": ["security", "oss"]
  }'
```

### CLI — Full Pipeline Scanner

The `scan_github_repo.py` script runs the complete pipeline: clone → build → scan → LLM enhance → RAG store → create GitHub Issues.

```bash
cd backend

# Full pipeline (scan + LLM + RAG + GitHub Issues)
python scan_github_repo.py <owner> <repo>

# Skip GitHub issue creation
python scan_github_repo.py <owner> <repo> --no-issues

# Skip RAG storage
python scan_github_repo.py <owner> <repo> --no-rag

# Custom scan types
python scan_github_repo.py <owner> <repo> --scan-types security oss deprecation
```

**Example:**
```bash
python scan_github_repo.py jay-nagulavancha spring-boot-spring-security-jwt-authentication
```

This will:
1. Fetch repository metadata from GitHub API
2. Clone the repo (shallow `--depth 1`)
3. Detect language (Java) → auto-detect Java 17 from `pom.xml` → build with Maven
4. Run SecurityAnalyzer (SpotBugs) and OSSAnalyzer (OWASP Dependency-Check)
5. Enhance report with LLM fix suggestions (if Ollama is running)
6. Store results in RAG (FAISS) for historical context
7. Create a GitHub Issue for critical/high findings
8. Save full report to `scan_report_<owner>_<repo>.json`

## 🏗️ Architecture

The platform uses a multi-agent architecture with LLM orchestration:

1. **API Layer** - FastAPI endpoints for scan and GitHub operations
2. **ScanService** - Main orchestration service
3. **Orchestrator Agent** - LLM-powered agent selection
4. **Specialized Analyzers** - Security, OSS, Change, Deprecation, GitHub
5. **LLM Service** - Report generation and recommendations
6. **RAG Service** - Historical context and pattern matching

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[backend/LLM_SETUP.md](backend/LLM_SETUP.md)** - LLM provider setup (Ollama, OpenAI)
- **[backend/MCP_GITHUB_SETUP.md](backend/MCP_GITHUB_SETUP.md)** - GitHub integration setup
- **[backend/JAVA_SCANNING_SETUP.md](backend/JAVA_SCANNING_SETUP.md)** - Java security scanning with SpotBugs
- **[backend/DEPENDENCY_SCANNING_SETUP.md](backend/DEPENDENCY_SCANNING_SETUP.md)** - Dependency vulnerability scanning with OWASP Dependency-Check

## 🔧 Configuration

### Environment Variables

```bash
# LLM Configuration
LLM_PROVIDER=ollama  # ollama, openai, huggingface
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://localhost:11434
OPENAI_API_KEY=your_key  # For OpenAI
OPENAI_MODEL=gpt-4o-mini

# GitHub Integration
GITHUB_TOKEN=your_github_token

# Vector Database
VECTOR_DB_TYPE=faiss  # faiss or qdrant
VECTOR_DB_DIR=.vector_db
QDRANT_URL=localhost
QDRANT_PORT=6333
```

### Health Check

```bash
curl http://localhost:8000/health
```

Returns status of all services:
- LLM availability and provider
- RAG service status
- GitHub integration status

## 🎯 Use Cases

### 1. Security Scanning
- **Static Analysis**: Detect vulnerabilities with Bandit (Python) and SpotBugs (Java)
- Get LLM-generated fix suggestions
- Create GitHub issues automatically

### 2. Dependency Vulnerability Scanning
- **Java/Maven**: Scan JAR dependencies for known CVEs using OWASP Dependency-Check
- **Python**: License information with pip-licenses
- **Vulnerability Detection**: Find CVEs in imported dependencies
- **CVSS Scoring**: Get severity ratings for vulnerabilities
- **License Compliance**: Check license compatibility

### 3. Code Change Analysis
- Track changes between commits/branches
- Generate release notes
- Identify breaking changes

### 4. Deprecation Detection
- Find deprecated code patterns
- Get migration recommendations
- Prioritize modernization efforts

### 5. GitHub Repository Analysis
- Analyze repositories without cloning
- Fetch code for analysis
- Create issues from scan results

## 🔌 API Endpoints

### Scan Endpoints
- `POST /api/scan` - Scan local repository
- `GET /api/scan/{scan_id}` - Get scan results

### GitHub Endpoints
- `GET /api/github/tools` - List available MCP tools
- `POST /api/github/analyze` - Analyze GitHub repository
- `POST /api/github/scan` - Prepare GitHub repo for scanning
- `POST /api/github/issue` - Create GitHub issue
- `POST /api/github/mcp/tool` - Call MCP tool directly
- `GET /api/github/repo/{owner}/{repo}/file` - Get file contents
- `GET /api/github/repo/{owner}/{repo}/commits` - Get commits

### Health
- `GET /` - Basic health check
- `GET /health` - Detailed service status

## 🛠️ Development

### Project Structure

```
backend/
├── app/
│   ├── agents/              # Analyzer implementations (+ orchestrator agent)
│   │   ├── orchestrator_agent.py   # LLM-powered agent selection
│   │   ├── security_agent.py       # SAST (Bandit + SpotBugs, auto-build)
│   │   ├── oss_agent.py            # SCA (pip-licenses + OWASP Dep-Check, auto-build)
│   │   ├── change_agent.py         # Git diff analysis
│   │   ├── deprecation_agent.py    # AST-based deprecation detection
│   │   └── github_agent.py         # MCP GitHub interactions
│   ├── services/            # Core services
│   │   ├── scan_service.py         # Full pipeline (scan + LLM + RAG + issues)
│   │   ├── llm_service.py          # Multi-provider LLM (Ollama/OpenAI/HF)
│   │   ├── rag_service.py          # Vector DB (FAISS/Qdrant)
│   │   └── mcp_github_service.py   # GitHub API via MCP
│   ├── utils/               # Utilities
│   │   ├── project_detector.py     # Language/build tool detection
│   │   └── project_builder.py      # Auto-build (Maven/Gradle + JDK resolution)
│   ├── api/                 # API routes
│   │   └── routes/
│   │       ├── scans.py
│   │       └── github.py
│   ├── models/              # Pydantic models
│   │   ├── scan.py
│   │   └── report.py
│   └── main.py              # FastAPI app
├── scan_github_repo.py      # CLI full-pipeline scanner
├── requirements.txt
├── Dockerfile               # Multi-stage (prod + dev)
├── .env.example
├── LLM_SETUP.md
├── MCP_GITHUB_SETUP.md
├── JAVA_SCANNING_SETUP.md
└── DEPENDENCY_SCANNING_SETUP.md
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

[Add your license here]

## 🙏 Acknowledgments

- **Ollama** - Open-source LLM runtime
- **Bandit** - Security linter
- **FAISS** - Vector similarity search
- **FastAPI** - Modern web framework

## 📞 Support

For issues and questions:
- Open an issue on GitHub
- Check documentation in `/backend` directory
- Review setup guides for specific features

---

**Built with ❤️ using multi-agent AI orchestration**
