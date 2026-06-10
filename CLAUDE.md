# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A multi-agent code intelligence platform: a FastAPI backend that clones/scans repos with security/dependency/IaC/secrets/container analyzers, runs an LLM-powered orchestrator to combine findings, stores history in a vector DB (RAG), and can autonomously open remediation pull requests. A React/Vite dashboard (frontend/) consumes the API.

## Commands

### Backend (run from `backend/`)

```bash
# Install deps
pip install -r requirements.txt

# Run the API server (hot reload)
uvicorn app.main:app --reload

# Run all tests
pytest

# Run a single test file / test / class
pytest tests/test_remediation_endpoint.py
pytest tests/test_remediation_endpoint.py::TestGetScan
pytest tests/test_remediation_endpoint.py::test_owner_repo_derived

# Full pipeline CLI: clone -> build -> scan -> LLM enhance -> RAG store -> open issues/PR
python scan_github_repo.py <owner> <repo>
python scan_github_repo.py <owner> <repo> --no-issues --no-rag
python scan_github_repo.py <owner> <repo> --scan-types security oss deprecation
```

Configuration is via `.env` in `backend/` (copy from `.env.example`). Key knobs: `LLM_PROVIDER` (ollama/groq/openai/huggingface/bedrock), `REMEDIATION_MODE` (deterministic/nondeterministic/claude_agent), `CLAUDE_AGENT_ENABLED`, `VECTOR_DB_TYPE` (faiss/qdrant), `GITHUB_TOKEN`, `LANGSMITH_TRACING`.

### Frontend (run from `frontend/`)

```bash
npm run dev       # Vite dev server on :5173
npm run build     # tsc -b && vite build
npm run preview
```

Set `VITE_API_BASE_URL` (defaults to `http://localhost:8000/api`); `frontend/src/services/api.ts` falls back to mock data when the API is unreachable.

### Docker

```bash
docker compose up -d                       # backend + Ollama (+ qdrant if profile)
docker compose --profile dev up -d         # hot-reload backend + Java scanning tools
docker compose --profile full up -d        # + Qdrant + frontend
docker compose exec backend python scan_github_repo.py <owner> <repo>
```

The Dockerfile is multi-stage: `production`, `development`, and `test` (runs the pytest suite — used in CI).

## Architecture

### Pipeline (ScanService — `app/services/scan_service.py`)

`ScanService` is the top-level orchestration entry point with two modes:
- `run_scan()` — scan a local repo path: RAG historical-context query → `OrchestratorAgent` runs analyzers → LLM enhancement (fix suggestions / summaries / release notes) → RAG storage.
- `scan_github_repo()` — full GitHub pipeline: fetch repo metadata → shallow clone (`--depth 1`) → `ProjectDetector`/`ProjectBuilder` auto-build Java projects → run analyzers → LLM enhance → RAG store → auto-create GitHub issues for critical/high findings → optional PR creation → cleanup temp clone.

Every scan gets a `scan_id` (uuid4) and is registered in the in-process `SCAN_STORE` dict in `app/api/routes/scans.py` (no DB — results don't survive a restart).

### Agents (`app/agents/`)

`OrchestratorAgent` decides which analyzers to run (scan_types is the fast path; LLM can additionally filter) and combines their outputs into one report via the LLM. It owns instances of:
- `SecurityAnalyzer` — Bandit (Python) / SpotBugs (Java), auto-builds Java via `ProjectBuilder`
- `OSSAnalyzer` — pip-licenses (Python) / OWASP Dependency-Check (Java), also auto-builds
- `ChangeAnalyzer` — git diff analysis
- `DeprecationAnalyzer` — AST-based deprecated-pattern detection
- `SecretsAnalyzer` — gitleaks
- `InfraAnalyzer` — checkov (IaC misconfiguration)
- `ContainerAnalyzer` — trivy (filesystem or `TRIVY_IMAGE`)
- `GitHubAnalyzer` — wraps `MCPGitHubService` for repo metadata/files/issues/PRs

`PRAgent` (`app/agents/pr_agent.py`) is the autonomous remediation/PR agent: applies conservative deterministic fixes for known patterns, can delegate to `ClaudeAgentService` (Claude Agent SDK) when `REMEDIATION_MODE=claude_agent`, validates via git diff/commit, and opens a PR through `MCPGitHubService`. `create_fix_pr()` is the main entry point, reachable via the CLI's `--create-pr`-style flag and via `POST /api/scan/{scan_id}/remediate`.

`architect.py` and `guardrail_agent.py` are stubs (not yet implemented) — don't assume they do anything.

### Services (`app/services/`)

- `LLMService` — multi-provider abstraction (Ollama default for dev, Groq, OpenAI, Hugging Face, Bedrock); generates fix suggestions / summaries / release notes / combined reports; degrades gracefully (returns raw structured data) when the LLM is unavailable; wraps calls in `LangSmithTracer` for optional observability. Prompt sizes are budgeted via `LLM_PROMPT_MAX_*` env vars to avoid 413/context-length errors.
- `RAGService` — FAISS (default, in-memory) or Qdrant vector store using `sentence-transformers/all-MiniLM-L6-v2` embeddings; stores scans and retrieves historical context/similar-scan patterns. Optional — pass `None` (or `--no-rag`) to disable.
- `MCPGitHubService` — GitHub REST API access modeled as MCP tools (get repo/file/commits/issues, create issue/PR, get diff).
- `ClaudeAgentService` — wraps the Claude Agent SDK to run an autonomous coding agent against a checked-out repo for remediation; gated by `CLAUDE_AGENT_ENABLED` + SDK availability (`is_available()`).
- `LangSmithTracer` — optional tracing wrapper around scan/LLM runs (`LANGSMITH_TRACING`).
- `agent_service.py` / `report_service.py` — currently stubs.

### Auto-build for Java (`app/utils/`)

`ProjectDetector` identifies language/build system from indicator files (`pom.xml` → Maven/Java, `build.gradle` → Gradle, `requirements.txt` → Python, etc.). `ProjectBuilder` then detects the required JDK version from `pom.xml`/`build.gradle`, resolves the right JDK via macOS `/usr/libexec/java_home` (falling back to scanning `/Library/Java/JavaVirtualMachines/`), prefers `mvnw`/`gradlew` wrappers, and runs `mvn compile -q -DskipTests` or `gradlew compileJava -q -x test` with a 10-minute timeout before SAST/SCA analyzers run.

### API layer (`app/api/routes/`)

- `scans.py` — `/api/scan` (run a scan), `/api/scan/{scan_id}` (lookup via `SCAN_STORE`), `/api/scan/{scan_id}/remediate` (drives `PRAgent.create_fix_pr()` against a fresh temp clone), plus dashboard endpoints (`/dashboard/summary`, `/dashboard/trends`, `/repos`, `/findings`) that the frontend consumes.
- `github.py` — `/api/github/*` for analyze/scan/issue creation/MCP tool invocation/file & commit retrieval.

`app/main.py` wires both routers and exposes `/` and `/health` (reports LLM/RAG/GitHub/LangSmith availability).

### Frontend (`frontend/src/`)

React + TypeScript + Vite + react-router. `pages/` (Dashboard, Findings, Repositories) call `services/api.ts`, which talks to the FastAPI backend at `VITE_API_BASE_URL` and falls back to in-file mock data if the request fails — useful for working on UI without a running backend.

## Working notes

- `.kiro/specs/` contains design/requirements docs for in-flight features (e.g. `remediation-api-endpoint`, `claude-agent-remediation`) — check there for the rationale behind recent additions to `scans.py` / `PRAgent` / `ClaudeAgentService` before changing them.
- `.kiro/steering/diagram-theme.md` defines the required visual style (colors, box types, layout) for any architecture diagrams or HTML visualizations created for this project — follow it exactly rather than inventing a new theme.
- `ARCHITECTURE.md` documents the original orchestrator+analyzer design; the agent roster has since grown (secrets/infra/container/PR agents, Claude Agent SDK remediation) — prefer reading the code in `app/agents/` and `app/services/` over relying solely on that doc.
- External scanning tools (Bandit, SpotBugs, OWASP Dependency-Check, gitleaks, checkov, trivy) are invoked via `subprocess` and degrade gracefully (return empty results) when not installed — see `JAVA_SCANNING_SETUP.md` and `DEPENDENCY_SCANNING_SETUP.md` for setup.
