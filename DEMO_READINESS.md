# Demo Readiness — Few Days Out

Use this doc for a short-window demo: what to implement, what to skip, and a tight presentation script. For deeper step-by-step flows (issues, PR modes, CLI), see [DEMO_PLAYBOOK.md](./DEMO_PLAYBOOK.md).

---

## 1) What to Implement Before Demo (Must-Have)

- **Stable happy path**
  - One command or API path scans a public repo end-to-end.
  - Output shows findings, LLM-enriched sections, and clear next steps.

- **Provider / model stability**
  - Lock a known-good profile: Groq *or* Bedrock (inference profile ARN if required).
  - Document the exact `.env` keys for the demo machine.

- **UI demo readiness** (if showing the dashboard)
  - Overview, Repositories, and Findings pages load without errors.
  - Filters work (severity, analyzer, repository); fallback data OK if API empty.

- **Remediation story** (even if not live)
  - Know how you trigger remediation (CLI flag, API, or saved output).
  - If live PR creation is risky, keep a **saved successful JSON** or screen recording as backup.

- **Observability**
  - One LangSmith project with tracing on; be able to open **one** trace for the demo scan.

- **Operational guardrails**
  - A **demo `.env`** or checklist of required vars (`GITHUB_TOKEN`, LLM, LangSmith optional).
  - Optional: `scripts/demo-start.sh` + `scripts/demo-preflight.sh` (not required for first pass—add when you have time).

---

## 2) Nice-to-Have (If Time Permits)

- Persist last N scan results (replace in-memory only store) so the UI always has data after restart.
- A “Demo sample” repo button or canned JSON in the UI.
- Export / download scan report from UI.

---

## 3) Do Not Do Before Demo

- Full production infra (EKS, full Terraform apply) unless already stable.
- Large refactors or new analyzer types.
- Heavy new auth/RBAC unless already done.

---

## 4) Three-Day Execution Plan

### Day 1

- Lock demo environment (local or EC2): `.env`, model/profile, region.
- Run the same scan **5 times**; fix any flake (timeouts, missing tools, wrong model ID).
- Fix the **top two** UX rough edges in the UI (loading, empty state, labels).

### Day 2

- Capture one **golden** scan output (JSON + optional LangSmith link) as fallback.
- Dry-run the full demo **twice**, timeboxed to **10–12 minutes**.
- Write down exact commands and URLs you will click.

### Day 3

- Copy and labels only (polish, no new features).
- Prepare fallbacks:
  - If Bedrock fails → switch to Groq (or vice versa) in one minute.
  - If GitHub fails → show saved remediation / issues output.

---

## 5) Short Presentation Outline (5–7 Minutes)

1. **Problem (~45 s)**  
   Security and dependency findings are fragmented; triage and remediation are slow and hard to audit.

2. **What we built (~60 s)**  
   An AI-assisted pipeline: scan → aggregate → prioritize → LLM-enriched guidance → optional remediation workflow → observability.

3. **Architecture (~60 s)**  
   Analyzers + orchestration + pluggable LLM (e.g. Groq / Bedrock) + GitHub integration + LangSmith traces.

4. **Live demo (~2.5–3 min)**  
   Trigger scan → show summary and findings → show LLM section → show remediation path (or backup) → open LangSmith trace.

5. **Value (~45 s)**  
   Faster triage, clearer actions, traceable AI steps for trust and debugging.

6. **Roadmap (~30 s)**  
   Queued workers, policy-driven routing, production deploy (ECS/EKS), persistence.

---

## 6) Demo Script (Talk Track)

Use this verbatim or shorten.

> “Today I’ll show how the platform scans a repository, surfaces security and OSS-related risk, and helps move from findings to action—with traceable AI steps.
>
> I’ll start from the dashboard and run a scan on this repository. The system runs analyzers, aggregates results, and enriches the report with LLM-generated recommendations and next steps.
>
> In Findings, I can filter by severity and analyzer, and drill into file-level issues to prioritize what matters first.
>
> Next, I’ll show how remediation fits in: the platform can apply conservative automated fixes or AI-assisted changes depending on mode, and tie outcomes back to GitHub where appropriate.
>
> Finally, I’ll open LangSmith. Each major step shows up as spans, which gives us transparency and makes debugging and trust conversations much easier.
>
> So the outcome is: from raw scan output to prioritized, explainable remediation guidance—in one workflow.”

---

## 7) Quick Pre-Demo Checklist (Day-Of)

- [ ] `GITHUB_TOKEN` valid; token not expired.
- [ ] LLM path works (one-line smoke: small `generate` or health).
- [ ] LangSmith optional: if on, project and API key correct.
- [ ] Java demo repo: SpotBugs / build tools available if you demo Java scans.
- [ ] Browser: UI URL bookmarked; backend URL / CORS OK if separate origins.
- [ ] Fallback: golden JSON + LangSmith screenshot or link.

---

## 8) Later Discussion (Placeholder)

Topics to refine when you pick up the demo again:

- Target audience (exec vs engineering) → adjust depth of architecture vs live demo.
- Single “hero” repo vs two repos (Java + Python).
- Whether to show remediation PR live or recorded only.
- Whether to emphasize cost (Groq vs Bedrock) or compliance (Bedrock).

---

*Last updated for planning; iterate in this file or in DEMO_PLAYBOOK.md as the demo solidifies.*
