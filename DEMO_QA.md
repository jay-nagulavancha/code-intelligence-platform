# Demo Q&A

Living document of likely demo questions and the answers we want to give.
Add a new entry whenever we anticipate (or get caught off guard by) a real
question. Keep entries grounded in what the platform actually does so
answers stay honest and consistent.

Companion to:
- [DEMO_READINESS.md](./DEMO_READINESS.md) — must-haves, day-of checklist.
- [DEMO_PLAYBOOK.md](./DEMO_PLAYBOOK.md) — step-by-step demo flow.

## Index

1. [How is this different from GitHub's Security tab (Dependabot, code scanning, secret scanning)?](#1-how-is-this-different-from-githubs-security-tab-dependabot-code-scanning-secret-scanning)
2. [How are we using RAG in the process?](#2-how-are-we-using-rag-in-the-process)
3. [Are we sharing the entire codebase with the LLM, or only part of it? Do we synthesize before sending and after receiving?](#3-are-we-sharing-the-entire-codebase-with-the-llm-or-only-part-of-it-do-we-synthesize-before-sending-and-after-receiving)
4. [What tools does the platform actually use?](#4-what-tools-does-the-platform-actually-use)

> Add new questions to the index as they are added below.

---

## 1) How is this different from GitHub's Security tab (Dependabot, code scanning, secret scanning)?

### One-liner (use this if asked in passing)

> "GitHub's Security tab is a per-repo *findings inbox*. Our platform sits a layer above: it aggregates findings from many tools — including ones GitHub doesn't run natively — prioritizes and explains them with an LLM, and turns them into remediation PRs and tests, with full LangSmith traces of every AI step. GitHub Advanced Security (GHAS) is a complement, not a competitor."

### Honest framing

GHAS and this platform mostly **complement** each other. GHAS is excellent at *detection and tracking inside one repo*. This platform is an *analysis-and-remediation orchestrator* across many tools and repos, with an AI layer for triage and fixes.

### What this platform actually wraps today

- **SAST**: Bandit, Semgrep, SpotBugs (Java)
- **OSS / SCA**: OWASP Dependency-Check, pip-licenses
- **IaC**: Checkov
- **Container**: Trivy (filesystem + image)
- **Secrets**: Gitleaks
- **Code change / modernization**: in-house ChangeAnalyzer, DeprecationAnalyzer, GitHubAnalyzer
- **Orchestration**: LLM-driven (Bedrock / Groq / OpenAI / Ollama), RAG over historical scans, LangSmith tracing, remediation PR agent (deterministic + AI-assisted modes), unit-test generation for fixes

### Comparison by axis

| Axis | GHAS (Dependabot + Code Scanning + Secret Scanning) | Code Intelligence Platform |
|---|---|---|
| **SAST engine** | CodeQL (first-party) + any SARIF upload | Bandit, Semgrep, SpotBugs — wrapped and normalized |
| **OSS / SCA** | Dependabot (GitHub Advisory DB) + dependency review | OWASP Dependency-Check (NVD) + pip-licenses |
| **IaC** | Not first-party (would need a SARIF upload of e.g. Checkov) | Checkov, native |
| **Container** | Not first-party scan; SARIF upload of Trivy etc. | Trivy (fs + image), native |
| **Secrets** | GitHub secret scanning + push protection (very strong, validity-checking partner program) | Gitleaks (rules-based) |
| **Where it runs** | Inside GitHub on push/PR/schedule | Anywhere — local CLI, backend service, ECS Fargate |
| **Findings UX** | Per-repo Security tab, dismissals, severity, alert dedup | Aggregated unified dashboard, filter by severity / analyzer / repo, plus LLM summary |
| **Triage / prioritization** | Severity, reachability (CodeQL), EPSS hints | LLM-driven critical issues, recommendations, next steps; RAG over historical scans for context |
| **Auto-remediation** | Dependabot version-bump PRs only; Copilot Autofix on some CodeQL alerts (paid GHAS) | Multi-analyzer remediation PR agent; deterministic-fix mode + AI-assisted mode; LLM-generated unit tests for fixes |
| **Cross-repo / portfolio view** | Org-level "Security overview" (GHAS) | Single dashboard, normalized schema across analyzers |
| **LLM observability** | None | LangSmith traces of every LLM call (prompt + output + span tree) |
| **LLM provider** | Vendor-locked to GitHub Copilot | Pluggable: Bedrock, Groq, OpenAI, Ollama |
| **Cost** | Free for public repos; **GHAS license required for private repos** | Open-source tools + your own LLM bill; no per-seat license |
| **Code locality** | Code must live on github.com / GHES | Works on local clones, mirrors, GitLab, Bitbucket |
| **Customization** | CodeQL queries, SARIF uploads | Add a new analyzer = drop in a class; orchestrator picks it up |
| **Operational maturity** | Battle-tested, alert lifecycle, SLAs, scale | Demo-stage; we own ops |

### Where GHAS clearly wins (acknowledge openly)

1. **Push protection for secrets** — GitHub blocks the commit server-side; nothing on this side can do that.
2. **CodeQL semantic analysis** — taint tracking, dataflow, reachability. Bandit/Semgrep are pattern-based and weaker for "is this XSS actually reachable?"
3. **Zero-friction onboarding** for repos already in GitHub.
4. **Alert lifecycle UX** — dismiss-with-reason, auto-close on PR merge, branch protection integration.
5. **Advisory database freshness** — GitHub's GHSA is curated and often beats raw NVD for accuracy and timing.

### Where this platform wins (lead with these)

1. **Multi-tool aggregation in one report** — GHAS gives you separate views per source. The orchestrator normalizes Bandit + Semgrep + SpotBugs + Trivy + Checkov + Dependency-Check + Gitleaks into one schema and one findings page. That's 7+ tools that would otherwise live in 7+ tabs / SARIF pipelines.
2. **LLM-synthesized triage** — "What are my top 3 risks this sprint?" GHAS makes you read every alert; this platform produces an executive summary and prioritized next steps.
3. **End-to-end remediation, not just detection** — the PR agent opens fix PRs (deterministic mode for safe changes, AI-assisted for harder ones) plus generated unit tests. GHAS only auto-PRs version bumps and (with paid Autofix) some single-file CodeQL fixes.
4. **Provider-agnostic and self-hostable** — Bedrock for regulated workloads, Ollama for air-gapped, Groq for low cost. GHAS is locked to GitHub.
5. **Beyond security** — `ChangeAnalyzer` and `DeprecationAnalyzer` add code-modernization signals (deprecated APIs, breaking-change risk) that GHAS doesn't address at all.
6. **Observability of the AI itself** — LangSmith traces every LLM step. When a security director asks *"how did the AI arrive at this fix?"*, we show the actual prompt, response, and span tree. Copilot Autofix is a black box.
7. **Works outside GitHub** — internal mirrors, GitLab, Bitbucket, local repos.

### If pushed: "Why not just use GHAS + Copilot Autofix?"

- GHAS Autofix is **single-file, single-tool, single-vendor**, and only for some CodeQL alerts.
- Multi-tool, multi-repo **prioritization across signals** is what most enterprises actually want; GHAS doesn't synthesize across tools.
- LLM choice matters for **cost, latency, and data residency**. Regulated orgs often can't ship code/data to GitHub Copilot but can use Bedrock inside their VPC.
- **Provider diversity is a moat**. When one model vendor degrades or raises prices, we swap; GHAS users can't.

### Demo risk to manage

If the audience is GHAS-heavy and loves the alert UX, lead with the **synthesis + remediation + observability** story rather than the "we also do SAST" story (where GHAS + CodeQL is genuinely stronger). Position this platform as **above** the scanner layer, not competing with it.

---

## 2) How are we using RAG in the process?

### One-liner (use this if asked in passing)

> "Every scan is embedded and stored in a vector store. New scans start with a project-name retrieval that warms up the historical context, then re-query *after* analyzers run using the actual issues — so the LLM grounds both the report summary and the vulnerability fix suggestions in past scans of the same project, calling out recurring patterns explicitly."

### Honest framing

RAG sits at both ends of the pipeline. It's used **twice per scan** (once before orchestration, once after) to retrieve historical context, and it's used **as grounding** for two LLM steps (the orchestrator's report and the vulnerability fix suggestions). All RAG calls are traced in LangSmith.

### How it flows today

```
[1. RAG warm-up query]  →  [2. orchestrate analyzers]  →  [2.5. RAG re-query w/ issues]  →  [3. LLM enhancement]  →  [4. RAG store]
```

1. **Warm-up retrieval** (`ScanService._query_rag`) — keyed on project name only (no issues yet). Fast; populates `project_context["historical_context"]` so the orchestrator's LLM report has *some* historical grounding.
2. **Orchestrate analyzers** — Bandit / Semgrep / SpotBugs / Trivy / Checkov / Dependency-Check / Gitleaks run in the orchestrator. The orchestrator's `combine_outputs` builds a compact summary of the warm-up history (top-2 similar scans, top-3 issues each, recurring-issue-type counts) and injects it into the report prompt — explicitly asking the LLM to call out recurring issues.
3. **Re-query with current issues** (`ScanService._query_rag_with_issues`) — re-embeds a query keyed on the actual issues now produced by the analyzers, so retrieval becomes *issue-pattern-similar*, not just project-name-similar. Updates `historical_context`.
4. **LLM enhancement** (`_enhance_with_llm`) — `suggest_vulnerability_fixes` receives the same compact RAG summary and is asked to mark suggestions as `recurring: true` when the vulnerability matches a past pattern.
5. **Store** — full scan upserted into FAISS / Qdrant for future scans.

### Embedding + vector store details

- Embedding model: **`sentence-transformers/all-MiniLM-L6-v2`** → 384-dim vectors.
- Vector DB: **FAISS** by default (`.vector_db/faiss.index` + `metadata.json` on disk) or **Qdrant** for shared environments (cosine distance).
- Document text per scan: `Scan ID … Project … Issues found: N` plus issue-type/message/package for the first 10 issues, optionally + first 5 code snippets truncated to 200 chars.

### What's actually different now (vs. status quo)

- **Before this work**: history was retrieved and surfaced to the user, but the orchestrator prompt explicitly stripped `historical_context`, and the vulnerability suggestions never received it. RAG was effectively a *display* feature.
- **After this work**: history is summarized into a compact, prompt-friendly object (top-N scans + top-N issues + recurring-pattern counts) and injected into both the orchestrator's report prompt and `suggest_vulnerability_fixes`. The model is explicitly instructed to call out recurring patterns. There is also a second RAG query *after* orchestration so the issue-aware retrieval makes it into the most expensive LLM step.

### Demo talking-point sequence

1. "Every scan is embedded and stored — FAISS locally, Qdrant in shared environments."
2. "When you start a new scan, we retrieve similar past scans of this project and surface them in the report immediately."
3. "After the analyzers run, we re-query with the actual issues — that's the *issue-pattern* retrieval, not just project-name."
4. "Both the LLM summary and the vulnerability fix suggestions get a compact rollup of that history and explicitly call out anything that's recurring across past scans."
5. "Open LangSmith — `scan.rag_context.io`, `scan.rag_context_refined.io`, and `scan.store_in_rag.io` are all spans, so you can see exactly what was retrieved and how the prompt was constructed."

### Where the alternative wins (be honest)

1. **Cold start** — for a brand-new repo with no history, the historical context block is empty (the helper returns `None`) and the prompt is unchanged. RAG only adds value once we have a few scans of the same or similar projects.
2. **Cross-project knowledge transfer** — today, retrieval is keyed mostly on project name + issue-pattern fingerprints from this project; we don't yet do "project A's log4j fix → suggest the same for project B" generalization. That's a roadmap item.

### Demo risk to manage

- If you demo on a fresh sandbox with no prior scans, the LangSmith trace will show empty RAG payloads — so do a "seed run" of one or two scans before the demo so the second/third run actually surfaces historical context.
- The prompt budget grew slightly. The recently raised `LLM_JSON_MAX_TOKENS=4096` keeps response truncation away, but watch the LangSmith trace once during dry-run to confirm prompt-token totals are still well under the model context window.

---

## 3) Are we sharing the entire codebase with the LLM, or only part of it? Do we synthesize before sending and after receiving?

### One-liner (use this if asked in passing)

> "We never upload the codebase. The orchestrator sends a structured summary of analyzer findings — counts, top issues, no file contents. The only path that ever sees source code is the AI fix path, and it's bounded: at most three files per scan, each truncated to a configurable byte budget, with a hard prompt-size cap on every call. Every fix candidate is then validated by AST parse and a `git diff` check before we keep it; failed candidates are rejected and the original file is restored byte-for-byte."

### Honest framing

There are exactly **seven LLM call sites** in the platform. Most send synthesized analyzer output, not source code. Only the AI code-fix and test-generation paths embed file contents, and those are now bounded at three layers (per-call compaction, top-level prompt-size guard, and a per-file head+tail truncator). All inputs and outputs flow through LangSmith for audit.

### What each prompt actually sends

| # | Where | Input to the LLM | Bound today |
|---|---|---|---|
| 1 | `OrchestratorAgent.combine_outputs` (the report) | Per-analyzer issue counts + top 3 issues per analyzer with whitelisted fields (`message, severity, file, line, bug_type, package, type`) + project metadata + compact RAG history rollup | Top-3-per-analyzer + field whitelist |
| 2 | `LLMService.suggest_vulnerability_fixes` | Compacted vulnerabilities (sorted by severity, top-K, heavy fields stripped, strings truncated) + RAG history rollup | `_compact` + `_fit_prompt` (recursive shrink to fit `LLM_PROMPT_MAX_CHARS=24000`) |
| 3 | `LLMService.summarize_deprecation_issues` | Same compaction pipeline | Same |
| 4 | `LLMService.generate_release_notes` | Same compaction pipeline applied to `changes ∪ issues` | Same |
| 5 | `PRAgent._generate_nondeterministic_candidate` (AI code fix) | One file at a time, content head+tail-truncated to `LLM_PROMPT_FILE_MAX_CHARS=12000` (default) + top 5 issues for that file | `REMEDIATION_MAX_FILES=3` files per scan + per-file byte cap + top-level prompt guard |
| 6 | `PRAgent._generate_test_candidate` (AI test gen) | Updated source + existing test file, both head+tail-truncated to half the per-file budget | Same caps |
| 7 | `PRAgent._build_review_body` (post-PR review) | Snippets of up to 5 changed files, hard-truncated to 1200 chars each | Bounded |

Above everything: `LLMService.generate()` enforces a top-level prompt-size guard. Any prompt exceeding `LLM_PROMPT_MAX_CHARS` is tail-preserved (closing instructions kept) with a warning log — catches every present-and-future caller, even ones that build their own prompts.

### Pre-send synthesis (what we do *before* sending)

1. **Field whitelisting** — orchestrator strips heavy/noisy fields and keeps only `message, severity, file, line, bug_type, package, type`. Project context drops `historical_context`, `build_result`, `repo_info`.
2. **Top-N truncation** — orchestrator: top 3 per analyzer; PR fix/test gen: top 5 issues per file.
3. **`_compact`** (LLMService) — sorts findings by severity, keeps top-K, drops a default heavy-key list (full CVE descriptions, references, raw CVSS objects), truncates remaining string fields to `LLM_PROMPT_MAX_STR_LEN=400`.
4. **`_fit_prompt`** (LLMService) — repeatedly shrinks `top_k` then `max_str_len` until the rendered prompt fits `LLM_PROMPT_MAX_CHARS=24000`. Last resort: hard-truncates with a marker.
5. **`truncate_code_blob`** (LLMService) — for embedded source/test files, keeps head + tail (where imports / closing braces live) up to `LLM_PROMPT_FILE_MAX_CHARS=12000` with a marker in the middle.
6. **RAG rollup compaction** — `summarize_historical_context` produces a tight summary: top 2 similar scans × top 3 issues each + top 5 recurring patterns.
7. **Strict JSON contract** — every JSON-mode prompt explicitly demands RFC 8259 with escaped inner quotes and no trailing commas.

### Post-receive synthesis / validation (what we do *after* receiving)

1. **Markdown stripping** — both `extract_json_from_llm` and `_extract_code_block_or_text` peel off ```` ```json ```` / ```` ``` ```` fences.
2. **Robust JSON parse** — `json.loads` → `json_repair` → in-house brace/bracket balancer → fallback to deterministic report.
3. **AST validation** for fix candidates — Python via `ast.parse`, Java via brace-balance check. Invalid candidates are rejected.
4. **Diff validation** — every AI-applied fix is re-checked with `git diff` to confirm a real change happened. If empty, rejected.
5. **Bounded retries** — `REMEDIATION_MAX_ATTEMPTS=2` per file; on full failure the original is restored byte-for-byte.
6. **Type validation** — orchestrator checks the result is a `dict`; `suggest_vulnerability_fixes` checks for a `list`; if not, falls back gracefully.
7. **413 / context-length retry** — if the provider returns HTTP 413 or a known context-length error code (`context_length_exceeded`, `request_too_large`, etc.), the call is retried once with the user message tail-truncated to half its size before surfacing a clear error.
8. **LangSmith tracing** — every prompt and response captured (with 1200-char trace truncation for readability) so any past call can be replayed and audited.

### Configuration knobs (env, no code changes needed)

| Env var | Default | Purpose |
|---|---|---|
| `LLM_PROMPT_MAX_ITEMS` | `25` | Max items kept by `_compact` |
| `LLM_PROMPT_MAX_STR_LEN` | `400` | Per-string truncation inside `_compact` |
| `LLM_PROMPT_MAX_CHARS` | `24000` | Hard ceiling on full prompt size |
| `LLM_PROMPT_FILE_MAX_CHARS` | `12000` | Per-embedded-file head+tail budget |
| `LLM_JSON_MAX_TOKENS` | `4096` | Response token ceiling for JSON-mode prompts |
| `REMEDIATION_MAX_FILES` | `3` | Max files the AI fix path will touch per scan |
| `REMEDIATION_MAX_ATTEMPTS` | `2` | Retries per file before restoring original |

### Where the alternative wins (acknowledge openly)

1. **Whole-repo context** — tools that copilot-fy entire IDE workflows (Cursor, Copilot, Claude Code) can reason across the full repo because they sit inside the editor with the developer driving and explicit cost/latency awareness. Our platform is batch and bounded, so cross-file reasoning is intentionally limited to one file at a time.
2. **Secret/PII redaction** — we don't yet pre-scan flagged file contents for secrets before sending. Bedrock keeps data in-region and doesn't train on it, so the risk is bounded — but this should be on the roadmap for any regulated workload.

### Where we win (lead with these)

1. **Hard prompt budgets at three layers** — per-call compaction, top-level guard, per-file truncation. Prompts cannot accidentally blow the context window or trigger 413s on Groq free tier.
2. **No-trust output validation** — every AI fix is parsed, diffed, and either accepted or fully reverted. The LLM never silently corrupts the working tree.
3. **Fully audit-able** — every prompt and response is in LangSmith. Easy to answer "what exactly did you send to Bedrock for this fix?" with a screenshot.
4. **Provider-agnostic** — Bedrock for regulated, Groq/OpenAI for cheap, Ollama for air-gapped. Same compaction and validation pipeline in front of all of them.

### Demo talking-point sequence (verbatim option)

> "We never upload the codebase. The orchestrator sends a structured summary of analyzer findings — counts, top issues per analyzer, no file contents. The only path that ever sees source code is the AI fix path, and it's bounded three ways: at most three files per scan, each truncated to 12,000 characters with head+tail preservation, and a hard 24,000-character cap on the whole prompt. If the LLM returns broken Python we reject it via AST parse, and a `git diff` check makes sure something actually changed. If it returns nothing or anything invalid, we restore the original file byte-for-byte. Every prompt and response is captured in LangSmith so we can audit exactly what went over the wire."

> "For regulated environments we run Bedrock in-region — your code never leaves your AWS account or feeds anyone's training data."

### Demo risk to manage

- If you demo on a brand-new repo with files larger than 12 KB, watch the LangSmith trace to confirm `truncate_code_blob` preserved the relevant section. If the fix relates to logic in the middle of a 50 KB file, you may want to bump `LLM_PROMPT_FILE_MAX_CHARS` for that demo.
- Don't set `LLM_PROMPT_MAX_CHARS` higher than the model's context window minus headroom (e.g. for Claude 3.5 Sonnet on Bedrock keep it well under 180 K characters; default 24 K is conservative).

---

## 4) What tools does the platform actually use?

### One-liner (use this if asked in passing)

> "Eight industry-standard open-source scanners running in parallel under our orchestrator — Bandit, Semgrep, SpotBugs, OWASP Dependency-Check, pip-licenses, Checkov, Trivy, and Gitleaks — plus a pluggable LLM layer (Bedrock / Groq / OpenAI / Hugging Face / Ollama), FAISS or Qdrant for RAG, and LangSmith for tracing. The orchestrator and PR agent are our own; the rest is best-of-breed OSS."

### Honest framing

Everything below is what's wired up *today* on `main`. Stubs (`ArchitectAgent`, `GuardrailAgent` — empty placeholders for future work) are listed honestly so we don't oversell.

### Static analysis (SAST)

| Tool | Language(s) | What it catches | Wrapped by | License |
|---|---|---|---|---|
| **Bandit** | Python | Common Python security anti-patterns (eval/exec, weak crypto, hardcoded passwords, insecure subprocess use). | `SecurityAnalyzer` | Apache 2.0 |
| **Semgrep** | Multi-language (Python, Java, JS, Go, ...) | Pattern-based and dataflow-lite SAST with a large community ruleset; complements Bandit by adding cross-cutting rules. | `SecurityAnalyzer` | LGPL 2.1 (Community) |
| **SpotBugs** | Java | Bytecode-level bug pattern detection on compiled `.class` files (null-pointer issues, resource leaks, common security bugs). | `SecurityAnalyzer` | LGPL 2.1 |

### Software composition (OSS / SCA)

| Tool | Scope | What it catches | Wrapped by | License |
|---|---|---|---|---|
| **OWASP Dependency-Check** | Java (Maven / Gradle), Node, Python, Ruby, etc. | Known-vulnerable dependencies via CPE matching against the NVD. | `OSSAnalyzer` | Apache 2.0 |
| **pip-licenses** | Python | License posture for installed Python packages (catches GPL/AGPL contamination in proprietary code, missing licenses, etc.). | `OSSAnalyzer` | MIT |

### Infrastructure-as-Code (IaC)

| Tool | Scope | What it catches | Wrapped by | License |
|---|---|---|---|---|
| **Checkov** | Terraform, CloudFormation, Kubernetes manifests, Helm charts, Dockerfiles, ARM templates | Misconfigurations against a large policy library (open security groups, unencrypted storage, public S3, missing IAM least-privilege, etc.). | `InfraAnalyzer` | Apache 2.0 |

### Container

| Tool | Scope | What it catches | Wrapped by | License |
|---|---|---|---|---|
| **Trivy** (filesystem mode + image mode) | Container images, OS packages, language deps inside images | CVEs in OS / language packages, misconfigs in Dockerfiles, exposed secrets. Fast, no external API needed. | `ContainerAnalyzer` | Apache 2.0 |

### Secrets

| Tool | Scope | What it catches | Wrapped by | License |
|---|---|---|---|---|
| **Gitleaks** | Repository contents and (optionally) git history | Hardcoded secrets via regex + entropy rules — AWS/GCP/Azure keys, API tokens, private keys, passwords. | `SecretsAnalyzer` | MIT |

### In-house analyzers (no external tool)

| Component | What it does | Notes |
|---|---|---|
| **ChangeAnalyzer** | `git diff` between base and head ref, normalized into per-file additions/deletions/line ranges. Feeds release-note generation. | Pure git, no third-party dependency. |
| **DeprecationAnalyzer** | Python AST-based detection of deprecated patterns (legacy class style, etc.). | Extension point for adding more Python anti-patterns. |
| **GitHubAnalyzer** | Repo metadata, issue history, recent commits via the MCP GitHub service. Surfaces project context to the LLM and is also used to create remediation issues / PRs. | Needs `GITHUB_TOKEN`. |
| **OrchestratorAgent** | Decides which analyzers to run, executes them in parallel, calls the LLM to synthesize a unified report, falls back deterministically on LLM failure. | The "brain" of the platform. |
| **PRAgent** | Two remediation modes — *deterministic* (safe, rules-based fixes per analyzer) and *AI-assisted* (LLM-generated whole-file fix candidates with AST + diff validation). Also generates unit tests for fixes and writes a post-PR LLM review comment. | Bounded by `REMEDIATION_MAX_FILES=3`. |

### LLM layer (pluggable)

| Provider | Adapter | Where it shines | Notes |
|---|---|---|---|
| **AWS Bedrock** | `_generate_bedrock` (Converse API) | Regulated workloads, in-region data residency, Anthropic Claude / Llama / etc. | Default in production. Optional `BEDROCK_INFERENCE_PROFILE_ARN` for cross-region inference profiles. |
| **Groq** | `_generate_openai_compat` | Fast, cheap, free tier; great for dev and CI. | OpenAI-compatible. Subject to free-tier 413 / rate limits — handled by our 413-retry path. |
| **OpenAI** | `_generate_openai_compat` | Production-grade, broad model selection. | Same OpenAI-compatible adapter as Groq. |
| **Hugging Face Inference** | `_generate_huggingface` | Wide model selection via HF router, useful for niche / open-weight models. | Cost depends on the model. |
| **Ollama** | `_generate_ollama` | Local / air-gapped, zero data egress. | Slower without a GPU; warmup helper bakes in keep-alive. |

The `LLMService.generate()` entry point is provider-agnostic; calling code never branches on provider.

### RAG / vector store

| Component | Role | Notes |
|---|---|---|
| **FAISS** | Default, local-disk vector store at `.vector_db/faiss.index`. | No external service required; ideal for dev and single-host. |
| **Qdrant** | Optional, remote vector store (cosine distance, HTTP API). | Switch via `vector_db_type="qdrant"` and `QDRANT_URL` / `QDRANT_PORT`. |
| **sentence-transformers `all-MiniLM-L6-v2`** | Embedding model — 384-dim. | Local, no API call. Loading-report noise is suppressed by `RAGService._suppress_noisy_loggers`. |

### Cross-cutting / supporting

| Component | Role | Notes |
|---|---|---|
| **LangSmith** | Tracing of every LLM call, RAG retrieval, and pipeline step (with input/output capture). | The audit story — every prompt and response is replayable from the dashboard. |
| **json-repair** | Fallback parser for malformed LLM JSON (truncated strings, missing commas, unescaped quotes). | Backed by an in-house brace/bracket balancer if the package isn't installed. |
| **MCP GitHub service** | Reads repo metadata, creates issues, opens PRs, posts review comments. | Auth via `GITHUB_TOKEN`. |
| **FastAPI + Pydantic** | API surface and request/response validation. | Standard. |

### Deliberate non-tools (be candid about gaps)

- **`ArchitectAgent` and `GuardrailAgent`** — empty stub classes today. Roadmap placeholders for architecture review and policy guardrails; do not include in the live demo's spoken narrative.
- **No native CodeQL / SAST-engine** of our own — we deliberately wrap OSS tools rather than reinvent. If pushed, this is a *feature*, not a gap: we layer aggregation + AI + remediation on top of the best detectors that already exist.

### Demo talking-point sequence (verbatim option)

> "Under the hood we orchestrate eight industry-standard scanners — Bandit and Semgrep for Python and multi-language SAST, SpotBugs for Java, OWASP Dependency-Check and pip-licenses for SCA and license posture, Checkov for IaC, Trivy for containers, and Gitleaks for secrets. They all run in parallel, and our orchestrator normalizes their output into one schema before the LLM sees a single line of it."

> "The LLM layer is pluggable — Bedrock for production, Groq for cost, Ollama for air-gapped — and every call is traced in LangSmith so you can audit exactly what the AI did and why."

### Demo risk to manage

- If asked about a tool we *don't* wrap (CodeQL, Snyk, Sonatype Nexus IQ, Black Duck), the honest answer is "not today, but the orchestrator is designed to plug in additional analyzers — it's a class drop-in." Don't promise specific timelines.
- If asked which *version* of a scanner we run, the answer is "whatever the demo machine has installed" — we wrap the binary, we don't pin. Worth flagging as a hardening item before any production rollout.

---

## Template — when adding new Q&A

```markdown
## N) Question text exactly as someone would ask it

### One-liner (use this if asked in passing)
> Single sentence we are happy to be quoted on.

### Honest framing
2–4 sentences of context that anchors the answer in what we actually do.

### Detailed answer
Bullets, table, or short prose. Keep it grounded — link to code, configs,
or the relevant analyzer if useful.

### Where the alternative wins (acknowledge openly)
1. ...

### Where we win (lead with these)
1. ...

### Demo risk to manage (optional)
Anything to avoid in the live talk track.
```

When adding an entry:
1. Append it under a new `## N) ...` heading.
2. Update the **Index** at the top with a markdown link to the new heading.
3. Prefer questions you have **actually heard** in past demos / 1:1s before
   inventing strawmen.
