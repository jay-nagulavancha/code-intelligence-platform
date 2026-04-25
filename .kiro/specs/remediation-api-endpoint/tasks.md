# Tasks: remediation-api-endpoint

## Task List

- [x] 1. Add SCAN_STORE and helper functions to scans.py
  - [x] 1.1 Add module-level `SCAN_STORE: Dict[str, Dict[str, Any]] = {}` dict to `backend/app/api/routes/scans.py`
  - [x] 1.2 Add `store_scan_result(scan_result)` helper that stores result keyed by `scan_id`
  - [x] 1.3 Add `get_scan_result(scan_id)` helper that returns the result or `None`
  - [x] 1.4 Update the existing `POST /api/scan` handler to call `store_scan_result()` after a successful `run_scan()`

- [x] 2. Add Pydantic models for the remediation endpoint
  - [x] 2.1 Add `RemediateRequest` model with fields: `remediation_mode` (optional str), `owner` (optional str), `repo` (optional str), `base_branch` (str, default `"main"`)
  - [x] 2.2 Add `field_validator` on `remediation_mode` that raises `ValueError` if the value is not `None`, `"deterministic"`, or `"nondeterministic"`
  - [x] 2.3 Add `RemediateResponse` model with fields: `scan_id`, `created`, `mode`, `branch` (optional), `pull_request` (optional dict), `reason` (optional str)

- [x] 3. Implement GET /api/scan/{scan_id}
  - [x] 3.1 Replace the current stub in `scans.py` with a handler that looks up `scan_id` in `SCAN_STORE`
  - [x] 3.2 Return HTTP 200 with the full scan result dict if found
  - [x] 3.3 Return HTTP 404 with `{"detail": "Scan <scan_id> not found"}` if not found

- [x] 4. Implement POST /api/scan/{scan_id}/remediate
  - [x] 4.1 Add the route handler `remediate_scan(scan_id, request: RemediateRequest)` to `scans.py`
  - [x] 4.2 Look up `scan_id` in `SCAN_STORE`; raise `HTTPException(404)` if absent
  - [x] 4.3 Resolve `owner` and `repo`: use request fields if provided, else split `scan_result["repository"]` on `"/"`; raise `HTTPException(422)` if still unresolved
  - [x] 4.4 Resolve `remediation_mode`: use `request.remediation_mode` if provided, else `os.getenv("REMEDIATION_MODE", "deterministic")`
  - [x] 4.5 Log `scan_id`, `owner/repo`, and `remediation_mode` at INFO level before invoking PRAgent
  - [x] 4.6 Clone the repository to a temp directory using `subprocess.run(["git", "clone", "--depth", "1", ...])` (mirror pattern from `ScanService._clone_repository`)
  - [x] 4.7 Instantiate `PRAgent()` and call `create_fix_pr(repo_path, owner, repo, scan_result, base_branch, remediation_mode=mode)` inside a `try/except/finally`
  - [x] 4.8 In the `finally` block, call `shutil.rmtree(temp_dir, ignore_errors=True)`
  - [x] 4.9 On success, log `created`, `mode`, `reason` at INFO level and return `RemediateResponse`
  - [x] 4.10 On exception, log at ERROR level with `scan_id` and raise `HTTPException(500, detail=str(e))`

- [x] 5. Wire up logging
  - [x] 5.1 Add `import logging` and `logger = logging.getLogger(__name__)` at the top of `scans.py`
  - [x] 5.2 Verify all log calls in the remediation handler use `logger.info` / `logger.error` (not `print`)

- [x] 6. Write tests
  - [x] 6.1 Write unit tests for `store_scan_result` and `get_scan_result` helpers
  - [x] 6.2 Write unit test for `GET /api/scan/{scan_id}` — found (200) and not found (404) cases
  - [x] 6.3 Write unit test for default mode resolution (env var set / unset)
  - [x] 6.4 Write unit test for `owner`/`repo` missing from both request and `repository` field → 422
  - [x] 6.5 Write unit test for `create_fix_pr()` returning `created=false` → HTTP 200
  - [x] 6.6 Write unit test for logging output using `caplog`
  - [x] 6.7 Write property test (Hypothesis) for Property 1: scan result store round-trip
  - [x] 6.8 Write property test for Property 2: missing scan_id returns 404 on both GET and POST
  - [x] 6.9 Write property test for Property 3: create_fix_pr called with correct arguments
  - [x] 6.10 Write property test for Property 4: response contains all required fields
  - [x] 6.11 Write property test for Property 5: owner/repo derived from repository field
  - [x] 6.12 Write property test for Property 6: invalid remediation_mode returns 422
  - [x] 6.13 Write property test for Property 7: PRAgent exception yields HTTP 500
