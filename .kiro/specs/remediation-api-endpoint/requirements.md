# Requirements Document

## Introduction

This feature exposes the existing `PRAgent` remediation capability via a new REST API endpoint: `POST /api/scan/{scan_id}/remediate`. Currently, auto-fix PR creation is only accessible through the CLI (`scan_github_repo.py`) or by passing `create_pr=True` to `ScanService.scan_github_repo()`. There is no way for API consumers (e.g., the frontend dashboard or CI integrations) to trigger remediation on demand after a scan has completed.

The endpoint must accept a `scan_id`, look up the associated scan result, invoke `PRAgent.create_fix_pr()` with the caller-supplied remediation mode, and return the PR creation outcome. Because scan results are not yet persisted, this feature also requires a lightweight in-memory scan result store so that completed scans can be retrieved by ID.

## Glossary

- **Remediation_API**: The new `POST /api/scan/{scan_id}/remediate` FastAPI endpoint defined in this document.
- **PRAgent**: The existing `backend/app/agents/pr_agent.py` class that applies code fixes and opens GitHub pull requests.
- **ScanService**: The existing `backend/app/services/scan_service.py` class that orchestrates the full scan pipeline.
- **Scan_Store**: A lightweight in-memory dictionary (keyed by `scan_id`) that persists scan results for the lifetime of the API process.
- **Remediation_Mode**: A string value of either `"deterministic"` or `"nondeterministic"` that controls how `PRAgent` generates fixes.
- **Scan_Result**: The dictionary returned by `ScanService.run_scan()` or `ScanService.scan_github_repo()`, containing `scan_id`, `raw_results`, `report`, and repository metadata.
- **RemediateRequest**: The Pydantic request body model for the remediation endpoint.
- **RemediateResponse**: The Pydantic response model returned by the remediation endpoint.

---

## Requirements

### Requirement 1: Scan Result Persistence

**User Story:** As an API consumer, I want completed scan results to be retrievable by scan ID, so that I can trigger remediation on a scan that was run earlier in the same session.

#### Acceptance Criteria

1. THE Scan_Store SHALL retain each Scan_Result in memory, keyed by its `scan_id`, for the lifetime of the API process.
2. WHEN `ScanService.run_scan()` completes successfully, THE Scan_Store SHALL store the returned Scan_Result under its `scan_id`.
3. WHEN `ScanService.scan_github_repo()` completes successfully, THE Scan_Store SHALL store the returned Scan_Result under its `scan_id`.
4. WHEN a `scan_id` is looked up in the Scan_Store and no matching entry exists, THE Scan_Store SHALL return a sentinel value indicating absence (e.g., `None`).
5. THE Scan_Store SHALL be shared across all requests within the same API process instance (i.e., a module-level or dependency-injected singleton).

---

### Requirement 2: Remediation Endpoint — Happy Path

**User Story:** As a developer or CI system, I want to POST to `/api/scan/{scan_id}/remediate` to trigger auto-fix PR creation for a completed scan, so that I can close the auto-fix loop without re-running the full scan.

#### Acceptance Criteria

1. THE Remediation_API SHALL accept `POST /api/scan/{scan_id}/remediate` requests.
2. WHEN a valid `scan_id` is provided and the Scan_Store contains the corresponding Scan_Result, THE Remediation_API SHALL invoke `PRAgent.create_fix_pr()` with the stored Scan_Result and the caller-supplied `remediation_mode`.
3. WHEN `PRAgent.create_fix_pr()` returns successfully, THE Remediation_API SHALL return HTTP 200 with a RemediateResponse body containing `scan_id`, `created`, `mode`, `branch`, `pull_request`, and `reason` fields.
4. WHERE the caller omits `remediation_mode` in the request body, THE Remediation_API SHALL default to the value of the `REMEDIATION_MODE` environment variable, falling back to `"deterministic"` if the variable is unset.
5. THE RemediateRequest body SHALL accept the following optional fields: `remediation_mode` (string), `owner` (string), `repo` (string), and `base_branch` (string, default `"main"`).
6. WHERE `owner` and `repo` are not supplied in the request body, THE Remediation_API SHALL attempt to derive them from the stored Scan_Result's `repository` field (format `"owner/repo"`).

---

### Requirement 3: Remediation Endpoint — Error Handling

**User Story:** As an API consumer, I want clear error responses when remediation cannot proceed, so that I can diagnose and correct the problem.

#### Acceptance Criteria

1. WHEN the `scan_id` path parameter does not match any entry in the Scan_Store, THE Remediation_API SHALL return HTTP 404 with a JSON body containing a `detail` field describing the missing scan.
2. WHEN the stored Scan_Result does not contain a resolvable `owner`/`repo` (neither from the request body nor from the `repository` field), THE Remediation_API SHALL return HTTP 422 with a `detail` field explaining that `owner` and `repo` are required.
3. IF `PRAgent.create_fix_pr()` raises an unhandled exception, THEN THE Remediation_API SHALL catch the exception, log it, and return HTTP 500 with a `detail` field containing the error message.
4. WHEN `PRAgent.create_fix_pr()` returns `{"created": false, ...}` without raising an exception, THE Remediation_API SHALL return HTTP 200 with the full RemediateResponse (including `created: false` and the `reason` field) rather than an error status.
5. IF the `remediation_mode` value supplied in the request body is not `"deterministic"` or `"nondeterministic"`, THEN THE Remediation_API SHALL return HTTP 422 with a `detail` field listing the accepted values.

---

### Requirement 4: GET /api/scan/{scan_id} Implementation

**User Story:** As an API consumer, I want `GET /api/scan/{scan_id}` to return the stored scan result, so that I can inspect a completed scan before deciding whether to remediate.

#### Acceptance Criteria

1. WHEN a `GET /api/scan/{scan_id}` request is received and the Scan_Store contains the matching entry, THE Remediation_API SHALL return HTTP 200 with the full Scan_Result JSON.
2. WHEN a `GET /api/scan/{scan_id}` request is received and the Scan_Store does not contain the matching entry, THE Remediation_API SHALL return HTTP 404 with a `detail` field describing the missing scan.

---

### Requirement 5: Remediation Mode Validation and Passthrough

**User Story:** As a developer, I want the remediation mode to be validated and correctly forwarded to the PRAgent, so that deterministic and nondeterministic fix strategies behave as documented.

#### Acceptance Criteria

1. THE Remediation_API SHALL pass the resolved `remediation_mode` value directly to `PRAgent.create_fix_pr()` as the `remediation_mode` argument.
2. WHEN `remediation_mode` is `"deterministic"`, THE PRAgent SHALL apply only conservative, pattern-based Java fixes (defensive copies, `hashCode` generation) as defined in the existing `PRAgent` implementation.
3. WHEN `remediation_mode` is `"nondeterministic"`, THE PRAgent SHALL invoke the LLM-assisted fix pipeline as defined in the existing `PRAgent` implementation.
4. THE RemediateResponse SHALL include a `mode` field reflecting the `remediation_mode` value that was actually used by `PRAgent`.

---

### Requirement 6: Observability and Logging

**User Story:** As a platform operator, I want remediation requests and outcomes to be logged, so that I can audit auto-fix activity and diagnose failures.

#### Acceptance Criteria

1. WHEN a remediation request is received, THE Remediation_API SHALL log the `scan_id`, resolved `owner/repo`, and `remediation_mode` at INFO level before invoking `PRAgent`.
2. WHEN `PRAgent.create_fix_pr()` returns, THE Remediation_API SHALL log the `created` flag, `mode`, and `reason` (if present) at INFO level.
3. IF `PRAgent.create_fix_pr()` raises an exception, THEN THE Remediation_API SHALL log the full exception at ERROR level including the `scan_id`.
4. THE Remediation_API SHALL use Python's standard `logging` module consistent with the rest of the backend codebase.
