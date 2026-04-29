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
