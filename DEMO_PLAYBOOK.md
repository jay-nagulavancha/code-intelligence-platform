# Code Intelligence Platform Demo Playbook

## 1) Demo Objective (30 seconds)

Show how the platform moves from:

1. repository scan  
2. analyzer findings  
3. LLM-enriched report  
4. GitHub issues  
5. remediation pull request  

using deterministic and non-deterministic remediation modes.

---

## 2) Pre-Demo Checklist

- In `backend/.env`, ensure:
  - `GITHUB_TOKEN` is set
  - LLM provider settings are valid (`LLM_PROVIDER`, provider API key)
  - Optional: `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY`
  - `REMEDIATION_MODE=deterministic` (or set per command)
- Tools installed for Java repos:
  - SpotBugs
  - OWASP Dependency-Check
  - Maven/Gradle + JDK

---

## 3) Demo Script (Step-by-Step)

Run from `backend/`.

### Step A - Baseline scan

```bash
python -u scan_github_repo.py <owner> <repo> --scan-types security oss deprecation --no-rag
```

What to explain:
- `ScanService` clones and detects project language.
- `OrchestratorAgent` runs analyzers.
- Output shows findings by severity/tool.

### Step B - GitHub issue automation

```bash
python -u scan_github_repo.py <owner> <repo> --scan-types security oss
```

What to explain:
- Critical/high findings are grouped and posted as GitHub issues.
- Issues include locations + AI recommendations (if LLM enabled).

### Step C - Deterministic remediation PR

```bash
python -u scan_github_repo.py <owner> <repo> --create-pr --remediation-mode deterministic --scan-types security --no-rag
```

What to explain:
- Rule-based safe fixes only.
- Branch -> commit -> push -> PR.
- If no fixable patterns are found, remediation is skipped with a reason.

### Step D - Non-deterministic remediation PR

```bash
python -u scan_github_repo.py <owner> <repo> --create-pr --remediation-mode nondeterministic --scan-types deprecation --no-rag
```

What to explain:
- LLM proposes file-level candidate fixes.
- Validation loop checks candidate quality before accepting.
- Only validated changes are committed and opened as PR.

---

## 4) Example End-to-End Data Flow (Component by Component)

Use this as the "how data flows" explanation in the demo.

### Input

CLI request:

```text
owner=jay-nagulavancha
repo=spring-boot-spring-security-jwt-authentication
scan_types=["security","oss","deprecation"]
create_pr=true
remediation_mode="nondeterministic"
```

### Flow

1. **CLI (`scan_github_repo.py`)**
   - Parses args and initializes services (`LLMService`, `MCPGitHubService`, optional `RAGService`).
   - Calls `ScanService.scan_github_repo(...)`.

2. **`ScanService.scan_github_repo()`**
   - Fetches repo metadata from GitHub.
   - Clones repo to temp directory.
   - Detects language with `ProjectDetector`.
   - Builds Java project if needed with `ProjectBuilder`.
   - Calls `run_scan(...)`.

3. **`ScanService.run_scan()`**
   - Optionally fetches historical context from `RAGService`.
   - Calls `OrchestratorAgent.orchestrate(...)`.
   - Registers analyzer-complete callback:
     - `PRAgent.engage_after_analyzer(...)` runs after each analyzer for remediation engagement summary.

4. **`OrchestratorAgent`**
   - Decides analyzers from `scan_types`.
   - Runs analyzers and collects `raw_results`:
     - `security` -> Bandit/SpotBugs findings
     - `oss` -> pip-licenses/Dependency-Check findings
     - `deprecation` -> AST findings
   - Combines analyzer outputs into unified report (LLM + fallback).

5. **LLM enhancement (`ScanService._enhance_with_llm`)**
   - Adds:
     - vulnerability suggestions
     - deprecation summary
     - release notes (if change data exists)

6. **GitHub issues (`ScanService._create_github_issues`)**
   - Extracts critical/high findings.
   - Creates issue(s) via `MCPGitHubService.create_issue(...)`.

7. **Remediation PR (`PRAgent.create_fix_pr`)**
   - Deterministic mode:
     - Applies rule-based safe fixes.
   - Non-deterministic mode:
     - Collects file-scoped issues.
     - Generates LLM candidate patch per file.
     - Validates candidate (syntax/structure + effective diff).
     - Retries per file based on `REMEDIATION_MAX_ATTEMPTS`.
   - On accepted changes:
     - creates branch
     - commits and pushes
     - opens PR via `MCPGitHubService.create_pull_request(...)`.

8. **RAG storage (`ScanService._store_in_rag`)**
   - Stores scan artifacts as embeddings for future retrieval.

9. **Output to CLI**
   - `scan_id`, summary report, raw analyzer outputs,
   - `github_issues_created`,
   - `remediation_by_analyzer`,
   - `remediation_pr`,
   - optional historical context.

---

## 5) Common Questions and Suggested Answers

- **Why analyzers and an orchestrator?**  
  Analyzers are deterministic scanners; orchestrator coordinates execution and LLM-driven report synthesis.

- **How do you prevent unsafe AI fixes?**  
  Non-deterministic mode has candidate validation gates and retry limits; deterministic mode is available for strict safety.

- **What if LLM is unavailable?**  
  Pipeline still runs with fallback structured outputs.

- **Where is observability?**  
  LangSmith traces are emitted when enabled.

---

## 6) Fast Command Cheat Sheet

```bash
# Full default pipeline
python -u scan_github_repo.py <owner> <repo>

# Deterministic remediation
python -u scan_github_repo.py <owner> <repo> --create-pr --remediation-mode deterministic --scan-types security

# Non-deterministic remediation
python -u scan_github_repo.py <owner> <repo> --create-pr --remediation-mode nondeterministic --scan-types deprecation
```

