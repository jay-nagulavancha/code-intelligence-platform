# Plan: Claude Agent SDK + AWS Bedrock for security remediation

This document captures the implementation plan to add **multi-step coding-agent remediation** (Claude Agent SDK) backed by **AWS Bedrock**, while reusing existing platform pieces: **`LLMService` (Bedrock Converse)** for single-shot tasks, **`PRAgent`** for git/PR workflows, and **Terraform/IAM** for Bedrock access.

## Goals

- **Trigger**: Remediation API, async job, or queue after a scan (same entry points as today).
- **Output**: Unchanged product contract — **clone → changes → validate → open PR** (reuse `MCPGitHubService` / existing PR flow).
- **New capability**: Optional remediation path that uses the **Claude Agent SDK** (multi-turn, file/tools) instead of **nondeterministic** mode’s single `llm_service.generate()` patch suggestions.

## Current codebase anchors

- **Bedrock today**: `backend/app/services/llm_service.py` — `_generate_bedrock` uses **Bedrock Runtime `converse`** with `BEDROCK_MODEL_ID`, optional `BEDROCK_INFERENCE_PROFILE_ARN`.
- **Remediation today**: `backend/app/agents/pr_agent.py` — `REMEDIATION_MODE` `deterministic` vs `nondeterministic`; nondeterministic path calls `LLMService.generate()` and applies extracted patches.
- **Infra**: Terraform notes Bedrock invoke permissions for the app task role (`infra/terraform/README.md`).

## Architecture choice: where the agent runs

**Recommended: separate remediation worker (Option A)**

- Small Python service/image with `claude-agent-sdk`, `git`, and minimal build tools (`mvn`, `npm`, etc.) as needed.
- API or queue **enqueues jobs** (repo URL, ref, finding payload, limits); worker runs the agent on a **clean clone**, then signals completion or opens the PR via existing GitHub integration.
- **Pros**: Isolates long runs, memory/CPU, and subprocess risk from the FastAPI process; easier timeouts and autoscaling.

**Alternative: in-process in API container (Option B)**

- Simpler wiring; higher risk of blocking, OOM, and tool abuse. Only viable for **heavily capped** short runs.

Pick one before implementation; it drives ECS/terraform layout.

## Bedrock and IAM

1. **Model IDs**: Confirm which Bedrock **Claude** model identifiers the **Agent SDK** expects vs current Converse `modelId` in `LLMService`. Align with [Claude Agent SDK — Python](https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-python) / [overview](https://docs.claude.com/en/agent-sdk/overview) for Bedrock auth and model configuration.
2. **Inference profiles**: If you use `BEDROCK_INFERENCE_PROFILE_ARN` for Converse, verify whether the Agent SDK path supports the same pattern or requires a different configuration.
3. **IAM**: Extend the task/worker role with least-privilege Bedrock actions on the **chosen model ARNs** (e.g. `bedrock:InvokeModel`, streaming variants if used). Reuse region and account patterns from existing Terraform variables (`bedrock_model_arn`, etc.).

## Implementation phases

### Phase 1 — Spike (prove the loop)

- Install `claude-agent-sdk` (Python) in a throwaway script or minimal container.
- Configure **Bedrock** per SDK docs (credentials via standard AWS chain: env/instance role).
- Run against a **fixture repo** with one synthetic finding; verify **file edits + optional test command** and a **git diff**.
- Document exact **model ID**, **region**, and any **SDK version** constraints (e.g. minimum version for a given Claude model).

### Phase 2 — Worker + job contract (if Option A)

- Define job schema: `job_id`, `clone_url`, `ref`, `finding_ids` or compact finding blob, `max_files`, `timeout_seconds`, `remediation_mode`.
- Add queue or internal API (SQS + ECS worker is a natural fit if you already use SQS in Terraform).
- Worker: clone → run agent → emit **structured result** (diff summary, files touched, command transcript) for audit.

### Phase 3 — Integrate with `PRAgent`

- Add a new mode, e.g. `REMEDIATION_MODE=claude_agent` (or `agent_bedrock`), distinct from `nondeterministic`.
- Flow:
  1. Checkout/clone (reuse existing git helpers in `PRAgent` where possible).
  2. Invoke **Claude Agent SDK** runner with **strict system instructions** (allowed paths, no secrets files, max churn).
  3. Reuse **post-agent validation**: existing diff checks, test hooks, retry limits — do not skip validation because the agent is “smarter.”
- Keep **`LLMService` + Bedrock** for summaries, ranking, and single-shot text; use **Agent SDK** only for multi-step code changes.

### Phase 4 — Configuration and docs

- Extend `backend/.env.example` (and worker env): `REMEDIATION_MODE`, Bedrock region, model/profile vars, agent **max turns**, **timeout**, **max files**, feature flag for enabling agent path.
- Optional: request body flag `use_claude_agent: true` for per-call override.

### Phase 5 — Observability and operations

- Log `job_id`, `run_id`, model id, duration, and outcome; wire to existing **LangSmith** tracing where practical (parent span per remediation job even if child spans differ from `LLMService`).
- Alerts on failure rate, token/cost estimates if available, and stuck jobs (timeout).

## Safety and governance (required)

- **Sandbox**: Agent runs only under a dedicated clone directory; no host filesystem escape.
- **Path allowlist**: Edits limited to repository paths relevant to supplied findings.
- **Tool allowlist**: If shell is enabled, restrict to commands you explicitly allow (`git status`, `mvn test`, `npm test`, etc.); deny network by default unless required.
- **Secrets**: No `.env` or key material in prompts; short-lived GitHub token only for PR push.
- **Merge policy**: PR from automation account + required human review + branch protection unchanged.

## Rollout

1. Feature flag off in production; enable for one internal repo.
2. Limit to narrow finding types (e.g. dependency bump or single-file Semgrep) before broader scope.
3. Red-team: prompt injection via finding text, path traversal in `file` fields, and command-injection in suggested fixes.

## Summary

| Component              | Role |
|------------------------|------|
| `LLMService` + Bedrock | Single-shot generation, reports, compact suggestions |
| Claude Agent SDK       | Multi-step remediation with tools on a clone |
| `PRAgent`              | Orchestration, validation, PR creation |
| Worker (recommended)   | Isolation, scaling, timeouts for agent runs |
| Terraform/IAM          | Bedrock permissions for worker/API as needed |

This file is a **planning artifact**; update it as the spike confirms Bedrock + Agent SDK configuration details and the chosen deployment option (A vs B).
