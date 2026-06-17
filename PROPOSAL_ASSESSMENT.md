# Security Scan & Remediation Pipeline — Proposal Assessment

_Assessment of the "Improved Flow and AI Agent Architecture" slide against the current `code-intelligence-platform` POC._
_Date: 2026-06-16_

---

## TL;DR

The idea is sound and the architecture is the right shape — it matches where the industry (Snyk, GitHub Advanced Security, Semgrep, Endor) is heading. The POC has already implemented the **hard middle of the pipeline**: multi-scanner orchestration, LLM analysis, RAG, autonomous code remediation via the Claude Agent SDK on Bedrock, and GitHub PR creation. That is roughly **60–65% of the steady-state value** and the most technically risky parts are done.

What's missing is mostly **productionization, not invention**: persistence, auth/multi-tenancy, an async job queue worker, real CI/CD integration, a genuine test/validation gate, and governance/audit. The slide also names several **commercial scanners (AWS Inspector, SonarQube, Prowler, Snyk, Checkmarx, Dependabot)** that are *not* in the code — the POC uses open-source equivalents (Bandit, Semgrep, SpotBugs, OWASP Dependency-Check, Checkov, Trivy, gitleaks). The capabilities overlap; the specific tools do not.

Rough effort to production-grade with a **2–3 engineer team: ~16–22 weeks** (≈4–5.5 months), detailed below.

---

## 1) Is the idea good? What's achievable, what isn't, how complete is the proposal?

### The idea
Strong and well-timed. "Scan → AI correlate/prioritize → AI remediate → PR → human approval → validate → deploy" is the correct end-to-end loop, and putting an LLM agent in the remediation seat (rather than just a rules engine like Dependabot) is the genuinely differentiated part. The slide's seven-step flow is coherent and maps cleanly onto real subsystems.

### What's clearly achievable (and largely proven in the POC)
- Multi-tool scanning across SAST, SCA/OSS, IaC, secrets, and containers.
- LLM-driven aggregation, deduplication, summarization, and fix-suggestion.
- Autonomous code remediation that opens a real PR — the POC does this today via deterministic fixes **and** the Claude Agent SDK.
- RAG over historical scans for context.
- Human-in-the-loop via PR review.

### What is harder / partially achievable — manage expectations
- **"Exploitability" and "production impact" prioritization** (Decision Engine). Real exploitability needs reachability analysis or EPSS/KEV enrichment; the POC currently prioritizes mostly on scanner severity. Achievable, but it's a project, not a checkbox.
- **"Automated final validation" with regression/integration tests** (Validation + step 6). Running a repo's own test suite reliably across arbitrary languages/build systems is genuinely hard. The POC validates via git diff/commit and optional re-scan, not by executing tests. The `guardrail_agent.py` is a stub.
- **AI code fixes that are always safe.** Works well for dependency bumps and known patterns; arbitrary business-logic fixes will need human review for the foreseeable future. The PR-approval gate is therefore load-bearing, not optional.

### What is essentially not addressed in the proposal as a *code* pipeline
- **Step 7 "Auto Deploy CI/CD and Release"** and the **Git/CI-CD integration band (Jenkins, GitHub Actions, GitLab CI)** — these are real-deployment concerns the POC has not touched at all.
- **Cloud-posture scanning (AWS Inspector, Prowler)** scans *running cloud infrastructure*, not repo code. That's a different data plane than everything else on the slide and effectively a separate product surface. The slide blends "scan my code" and "scan my cloud" into one layer; in practice they are two pipelines.

### Completeness of the proposal as a design doc
**~70% complete as a vision, ~40% complete as a buildable spec.** It's an excellent one-slide north star. As an engineering spec it omits the things that decide success/failure in production: data model & persistence, authentication/authorization & multi-tenancy, async job processing at scale, audit/compliance evidence storage, secrets management, cost controls per scan, SLAs, and a concrete tool-selection decision (commercial vs OSS scanners — they have very different licensing, cost, and integration implications).

---

## 2) How much is covered in the code today? What's pending?

Legend: ✅ built · 🟡 partial · ⛔ not started · 📦 provisioned but not wired

### Scanner Integration Layer
| Slide says | In the POC | Status |
|---|---|---|
| OSS scan (AWS Inspector) | OWASP Dependency-Check + grype fallback, pip-licenses | 🟡 capability yes, **Inspector no** |
| SAST (SonarQube) | Bandit, Semgrep, SpotBugs | 🟡 capability yes, **SonarQube no** |
| IaC scan (Terraform Scanner) | Checkov (covers Terraform/IaC) | ✅ capability covered |
| Infrastructure scan (Prowler) | — | ⛔ cloud-posture not built |
| Snyk / Checkmarx / Dependabot | OSS equivalents above; homegrown auto-issue/PR | 🟡 / ⛔ commercial tools not integrated |
| Trivy | `container_agent.py` | ✅ built |

### AI Analysis & Remediation Layer
| Engine (slide) | In the POC | Status |
|---|---|---|
| AI Reasoning (context, correlate, dedup, prioritize, map-to-code) | `OrchestratorAgent` + `LLMService` combine findings | 🟡 dedup/correlation is light |
| Decision (must-fix vs low, exploitable, prod impact, compliance) | severity-based routing | 🟡 no real exploitability/EPSS/compliance mapping |
| Remediation (code fixes, dep upgrades, IaC, config hardening) | `PRAgent` deterministic fixes + Claude Agent SDK | ✅ strong; IaC remediation thin |
| Validation (lint, unit/integration tests, regression, policy, build) | git diff/commit validation, optional re-scan | 🟡 no test execution / regression gate; `guardrail_agent` stub |

### LLM Model & Tools
| Slide | POC | Status |
|---|---|---|
| Claude SDK (Sonnet) via Amazon Bedrock | `ClaudeAgentService` + `CLAUDE_CODE_USE_BEDROCK`, Bedrock in `LLMService` | ✅ built |
| Context (standards, rules, source) + Knowledge/Skills (.md) | RAG context; some prompt context | 🟡 partial; no formal policy/standards corpus |
| RAG | `RAGService` (FAISS default / Qdrant) | ✅ built |

### Git & CI/CD Integration
| Slide | POC | Status |
|---|---|---|
| Creates branches / generates PRs | `MCPGitHubService` + `PRAgent` | ✅ built |
| Attaches evidence / explains remediations | PR body with rationale | 🟡 partial |
| Jenkins / GitHub Actions / GitLab CI | — (no `.github/workflows` in repo) | ⛔ not built |
| GitHub / GitLab APIs | GitHub REST via MCP service | 🟡 GitHub yes, GitLab no |

### Seven-step flow
1. Automated scans & report — ✅
2. AI analysis & risk prioritization — 🟡
3. AI automated code remediation & testing — ✅ remediation / 🟡 testing
4. Automated PR generation — ✅
5. Human approval & governance — 🟡 (PR review exists; no RBAC/approval workflow/audit)
6. Automated final validation — 🟡/⛔ (stub)
7. Auto deploy CI/CD & release — ⛔

### Cross-cutting production gaps (the real pending list)
- **Persistence:** scans live in an in-memory `SCAN_STORE` dict (`scans.py`) — lost on restart. RDS Postgres exists in Terraform but is **📦 not wired to the app**.
- **Auth/AuthZ:** **none.** No API auth, no RBAC, no multi-tenancy, no per-user/per-repo scoping.
- **Async processing:** SQS queue is **📦 provisioned in Terraform but there is no worker/consumer** in the code — scans run inline in the request.
- **CI/CD:** no pipeline in the repo (`.github/workflows` absent); the platform isn't triggerable from CI nor does it deploy itself.
- **Testing:** a single test file (`test_remediation_endpoint.py`, ~394 lines). No coverage for analyzers, orchestrator, LLM service, RAG, or frontend.
- **Secrets management:** `.env` files; no vault/Secrets Manager integration in app.
- **Observability:** LangSmith tracing only; no metrics, dashboards, alerting, or structured logging pipeline.
- **Stubs to finish or remove:** `architect.py`, `guardrail_agent.py`, `agent_service.py`, `report_service.py`, `analysis/ast_parser.py`, `dependency_graph.py`, `diff_engine.py`, `git_utils.py`, `file_utils.py`.
- **Infra hardening:** ECS tasks run in public subnets with public IPs; needs private subnets + VPC endpoints, WAF, TLS/ACM on the ALB (currently HTTP listener only).
- **Frontend:** functional dashboard with mock-data fallback; no auth, real-time, or production API contract hardening.

**Net:** the differentiated core (orchestration + AI remediation + PR) is **built and is the hard part**. The pending work is the "boring" production scaffolding plus the deploy/validation tail of the slide.

---

## 3) Tasks & estimates to production-grade

Estimates are **engineer-weeks (EW)** assuming mid/senior engineers. Ranges reflect uncertainty. Assumes a **2–3 person team** working partly in parallel; calendar time at the end.

### A. Data & State (foundational)
| Task | EW |
|---|---|
| Postgres data model (scans, findings, repos, remediations, audit) + migrations (Alembic) | 2–3 |
| Wire app to RDS; replace in-memory `SCAN_STORE`; repository pattern | 2 |
| Persist RAG/vector store durably (managed Qdrant or pgvector) | 1–2 |
| **Subtotal** | **5–7** |

### B. Async job processing & scale
| Task | EW |
|---|---|
| SQS consumer/worker service; move scans off the request path | 2–3 |
| Job lifecycle (queued/running/failed/retry), idempotency, dead-letter handling | 1–2 |
| Per-scan timeouts, concurrency limits, cost guardrails (LLM token budgets) | 1–2 |
| **Subtotal** | **4–7** |

### C. AuthN / AuthZ / Multi-tenancy
| Task | EW |
|---|---|
| API authentication (OIDC/SSO or API keys) + middleware | 1.5–2 |
| RBAC + tenant/org scoping on all data and endpoints | 2–3 |
| Secrets management (AWS Secrets Manager) for tokens/keys | 1 |
| **Subtotal** | **4.5–6** |

### D. AI quality: prioritization & validation (the differentiator)
| Task | EW |
|---|---|
| Decision Engine: EPSS/KEV + CVSS enrichment, exploitability/reachability heuristics, compliance mapping | 3–4 |
| Validation Engine: run repo build + test suite in sandbox, gate PRs on green | 3–5 |
| Finish `guardrail_agent` (policy checks) + correlation/dedup improvements | 2–3 |
| Remediation hardening: broaden safe-fix patterns, rollback, eval harness for fix quality | 2–3 |
| **Subtotal** | **10–15** |

### E. CI/CD integration & deploy (slide steps 6–7)
| Task | EW |
|---|---|
| Trigger integrations: GitHub Actions / GitLab CI / Jenkins webhooks + status checks | 2–3 |
| Evidence attachment + remediation explanations on PRs/checks | 1–2 |
| Self-deploy CI/CD for the platform (build → ECR → ECS) | 1–2 |
| (Optional) GitLab API parity with GitHub | 2–3 |
| **Subtotal** | **6–10** |

### F. Infrastructure hardening & ops
| Task | EW |
|---|---|
| Network hardening: private subnets, VPC endpoints, WAF, ALB TLS/ACM | 2–3 |
| Observability: metrics, structured logs, dashboards, alerting (CloudWatch/Grafana) | 2–3 |
| IaC completion: env separation (dev/stage/prod), remote state, CI for Terraform, least-privilege IAM review | 2–3 |
| Reliability: health checks, autoscaling, backups/DR, runbooks | 1–2 |
| **Subtotal** | **7–11** |

### G. Testing & quality (cross-cutting — do alongside everything)
| Task | EW |
|---|---|
| Unit tests for analyzers, orchestrator, services, PR agent (target ~70%+) | 3–4 |
| Integration/e2e tests for the full pipeline incl. mocked GitHub/LLM | 2–3 |
| Security review of the platform itself (it handles tokens + writes code) + load testing | 2–3 |
| Frontend tests + auth integration + API contract hardening | 1–2 |
| **Subtotal** | **8–12** |

### Estimate roll-up
| Workstream | EW (low–high) |
|---|---|
| A. Data & State | 5–7 |
| B. Async & Scale | 4–7 |
| C. Auth & Tenancy | 4.5–6 |
| D. AI Quality | 10–15 |
| E. CI/CD & Deploy | 6–10 |
| F. Infra & Ops | 7–11 |
| G. Testing & Quality | 8–12 |
| **Total** | **~44.5–68 engineer-weeks** |

**Calendar with a 2–3 engineer team (with parallelism): ≈ 16–22 weeks (~4–5.5 months)** to a solid production v1.

### Suggested phasing
- **Phase 1 — Production foundation (≈4–6 wks):** A + C + minimal G. Persistence, auth, secrets, basic test coverage. Makes it deployable and safe for real repos.
- **Phase 2 — Scale & deploy (≈4–6 wks):** B + E + F core. Async workers, CI/CD triggers, hardened infra, observability.
- **Phase 3 — AI differentiation (≈6–8 wks):** D + remaining G. Real prioritization, test-gated validation, fix-quality evals. This is where the product stops being "AI Dependabot" and becomes defensible.

### Key decisions to lock before estimating tighter
1. **Commercial vs OSS scanners** — does the org actually want Snyk/SonarQube/Checkmarx/Inspector (licensing + cost + integration EW), or are the OSS equivalents already in the POC acceptable? This single decision swings scope materially.
2. **Code-only vs code + cloud-posture** — including Inspector/Prowler adds a whole second pipeline; recommend deferring to a later phase.
3. **Single-tenant internal tool vs multi-tenant SaaS** — drives how much of workstream C is needed.
4. **Languages in scope** — the test-execution validation (D) cost scales with how many language/build ecosystems you must support reliably.

---

## Bottom line
The proposal is a strong, realistic vision and the POC has already de-risked the hardest, most novel piece (AI orchestration + autonomous remediation + PR, on Bedrock). The road to production is mostly disciplined engineering — persistence, auth, async, CI/CD, validation, hardening, and testing — not research. Budget roughly **4–5.5 months with 2–3 engineers**, front-loading the production foundation so the impressive AI core can run safely against real repositories.
