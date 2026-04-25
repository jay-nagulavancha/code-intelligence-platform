"""
Tests for the remediation API endpoint.
Covers unit tests and property-based tests (Hypothesis) for:
  - store_scan_result / get_scan_result helpers
  - GET /api/scan/{scan_id}
  - POST /api/scan/{scan_id}/remediate
"""
import os
import logging
import pytest
from unittest.mock import patch, MagicMock, ANY
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from app.main import app
from app.api.routes.scans import store_scan_result, get_scan_result, SCAN_STORE

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    """Clear SCAN_STORE before and after every test."""
    SCAN_STORE.clear()
    yield
    SCAN_STORE.clear()


def _make_pr_mock(created=True, mode="deterministic", branch="fix/branch",
                  pull_request=None, reason=None):
    """Return a MagicMock PRAgent instance whose create_fix_pr returns a preset dict."""
    mock_instance = MagicMock()
    mock_instance.create_fix_pr.return_value = {
        "created": created,
        "mode": mode,
        "branch": branch,
        "pull_request": pull_request or {"number": 1, "html_url": "https://github.com/o/r/pull/1"},
        "reason": reason,
    }
    return mock_instance


def _patch_remediate(mock_instance):
    """Context-manager helper: patches PRAgent and subprocess.run for remediate calls."""
    return (
        patch("app.api.routes.scans.PRAgent", return_value=mock_instance),
        patch("app.api.routes.scans.subprocess.run",
              return_value=MagicMock(returncode=0, stderr="")),
    )


# ---------------------------------------------------------------------------
# 6.1  Unit tests: store_scan_result / get_scan_result helpers
# ---------------------------------------------------------------------------

class TestStoreHelpers:
    def test_store_and_retrieve(self):
        result = {"scan_id": "abc-123", "data": "value"}
        store_scan_result(result)
        assert get_scan_result("abc-123") == result

    def test_missing_returns_none(self):
        assert get_scan_result("nonexistent") is None

    def test_store_without_scan_id_is_noop(self):
        store_scan_result({"data": "no-id"})
        assert len(SCAN_STORE) == 0

    def test_overwrite_existing(self):
        store_scan_result({"scan_id": "x", "v": 1})
        store_scan_result({"scan_id": "x", "v": 2})
        assert get_scan_result("x")["v"] == 2


# ---------------------------------------------------------------------------
# 6.2  Unit tests: GET /api/scan/{scan_id}
# ---------------------------------------------------------------------------

class TestGetScan:
    def test_found_returns_200(self):
        store_scan_result({"scan_id": "s1", "result": "ok"})
        resp = client.get("/api/scan/s1")
        assert resp.status_code == 200
        assert resp.json()["scan_id"] == "s1"

    def test_not_found_returns_404(self):
        resp = client.get("/api/scan/does-not-exist")
        assert resp.status_code == 404
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# 6.3  Unit test: default mode resolution (env var set / unset)
# ---------------------------------------------------------------------------

class TestDefaultModeResolution:
    def test_env_var_unset_defaults_to_deterministic(self):
        store_scan_result({"scan_id": "m1", "repository": "owner/repo"})
        mock_inst = _make_pr_mock(mode="deterministic")
        with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
             patch("app.api.routes.scans.subprocess.run",
                   return_value=MagicMock(returncode=0, stderr="")), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REMEDIATION_MODE", None)
            resp = client.post("/api/scan/m1/remediate", json={})
        assert resp.status_code == 200
        _, kwargs = mock_inst.create_fix_pr.call_args
        assert kwargs["remediation_mode"] == "deterministic"

    def test_env_var_set_uses_env_value(self):
        store_scan_result({"scan_id": "m2", "repository": "owner/repo"})
        mock_inst = _make_pr_mock(mode="nondeterministic")
        with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
             patch("app.api.routes.scans.subprocess.run",
                   return_value=MagicMock(returncode=0, stderr="")), \
             patch.dict(os.environ, {"REMEDIATION_MODE": "nondeterministic"}):
            resp = client.post("/api/scan/m2/remediate", json={})
        assert resp.status_code == 200
        _, kwargs = mock_inst.create_fix_pr.call_args
        assert kwargs["remediation_mode"] == "nondeterministic"

    def test_request_mode_overrides_env_var(self):
        store_scan_result({"scan_id": "m3", "repository": "owner/repo"})
        mock_inst = _make_pr_mock(mode="deterministic")
        with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
             patch("app.api.routes.scans.subprocess.run",
                   return_value=MagicMock(returncode=0, stderr="")), \
             patch.dict(os.environ, {"REMEDIATION_MODE": "nondeterministic"}):
            resp = client.post("/api/scan/m3/remediate",
                               json={"remediation_mode": "deterministic"})
        assert resp.status_code == 200
        _, kwargs = mock_inst.create_fix_pr.call_args
        assert kwargs["remediation_mode"] == "deterministic"


# ---------------------------------------------------------------------------
# 6.4  Unit test: owner/repo missing from both request and repository → 422
# ---------------------------------------------------------------------------

class TestOwnerRepoMissing:
    def test_no_owner_repo_no_repository_field_returns_422(self):
        store_scan_result({"scan_id": "nr1"})
        resp = client.post("/api/scan/nr1/remediate", json={})
        assert resp.status_code == 422

    def test_repository_without_slash_returns_422(self):
        store_scan_result({"scan_id": "nr2", "repository": "noslash"})
        resp = client.post("/api/scan/nr2/remediate", json={})
        assert resp.status_code == 422

    def test_empty_repository_returns_422(self):
        store_scan_result({"scan_id": "nr3", "repository": ""})
        resp = client.post("/api/scan/nr3/remediate", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6.5  Unit test: create_fix_pr returning created=false → HTTP 200
# ---------------------------------------------------------------------------

class TestCreatedFalse:
    def test_created_false_still_returns_200(self):
        store_scan_result({"scan_id": "cf1", "repository": "owner/repo"})
        mock_inst = _make_pr_mock(created=False, mode="deterministic",
                                  branch=None, pull_request=None,
                                  reason="No actionable issues found")
        with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
             patch("app.api.routes.scans.subprocess.run",
                   return_value=MagicMock(returncode=0, stderr="")):
            resp = client.post("/api/scan/cf1/remediate", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is False
        assert body["reason"] == "No actionable issues found"


# ---------------------------------------------------------------------------
# 6.6  Unit test: logging output using caplog
# ---------------------------------------------------------------------------

class TestLogging:
    def test_info_logged_before_pr_agent(self, caplog):
        store_scan_result({"scan_id": "log1", "repository": "owner/repo"})
        mock_inst = _make_pr_mock()
        with caplog.at_level(logging.INFO, logger="app.api.routes.scans"), \
             patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
             patch("app.api.routes.scans.subprocess.run",
                   return_value=MagicMock(returncode=0, stderr="")):
            client.post("/api/scan/log1/remediate", json={})
        messages = " ".join(caplog.messages)
        assert "log1" in messages
        assert "owner" in messages
        assert "repo" in messages

    def test_error_logged_on_pr_agent_exception(self, caplog):
        store_scan_result({"scan_id": "log2", "repository": "owner/repo"})
        mock_inst = MagicMock()
        mock_inst.create_fix_pr.side_effect = RuntimeError("boom")
        with caplog.at_level(logging.ERROR, logger="app.api.routes.scans"), \
             patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
             patch("app.api.routes.scans.subprocess.run",
                   return_value=MagicMock(returncode=0, stderr="")):
            client.post("/api/scan/log2/remediate", json={})
        assert any("log2" in m for m in caplog.messages)
        assert any("boom" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# 6.7  Property 1: scan result store round-trip
# Validates: Requirements 1.1, 1.2, 1.3, 4.1
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 1: scan result store round-trip
@given(
    scan_id=st.uuids().map(str),
    extra=st.fixed_dictionaries({"key": st.text(max_size=20)}),
)
@settings(max_examples=100, deadline=None)
def test_store_roundtrip(scan_id, extra):
    """Validates: Requirements 1.1, 1.2, 1.3, 4.1"""
    result = {**extra, "scan_id": scan_id}
    store_scan_result(result)
    assert get_scan_result(scan_id) == result
    # Also verify via HTTP
    resp = client.get(f"/api/scan/{scan_id}")
    assert resp.status_code == 200
    assert resp.json()["scan_id"] == scan_id


# ---------------------------------------------------------------------------
# 6.8  Property 2: missing scan_id returns 404 on both GET and POST
# Validates: Requirements 3.1, 4.2
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 2: missing scan_id returns 404
@given(scan_id=st.uuids().map(str))
@settings(max_examples=100)
def test_missing_scan_id_404(scan_id):
    """Validates: Requirements 3.1, 4.2"""
    # scan_id is guaranteed absent because clear_store fixture runs before each test
    resp_get = client.get(f"/api/scan/{scan_id}")
    resp_post = client.post(f"/api/scan/{scan_id}/remediate", json={})
    assert resp_get.status_code == 404
    assert "detail" in resp_get.json()
    assert resp_post.status_code == 404
    assert "detail" in resp_post.json()


# ---------------------------------------------------------------------------
# 6.9  Property 3: create_fix_pr called with correct arguments
# Validates: Requirements 2.2, 5.1
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 3: create_fix_pr called with correct arguments
@given(
    mode=st.sampled_from(["deterministic", "nondeterministic"]),
    owner=st.text(min_size=1, max_size=20,
                  alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"),
                                         whitelist_characters="-_")),
    repo=st.text(min_size=1, max_size=20,
                 alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"),
                                        whitelist_characters="-_")),
)
@settings(max_examples=100)
def test_correct_args_passed(mode, owner, repo):
    """Validates: Requirements 2.2, 5.1"""
    scan_id = "prop3-test"
    scan_result = {"scan_id": scan_id, "repository": f"{owner}/{repo}"}
    store_scan_result(scan_result)
    mock_inst = _make_pr_mock(mode=mode)
    with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
         patch("app.api.routes.scans.subprocess.run",
               return_value=MagicMock(returncode=0, stderr="")):
        resp = client.post(f"/api/scan/{scan_id}/remediate",
                           json={"remediation_mode": mode})
    assert resp.status_code == 200
    mock_inst.create_fix_pr.assert_called_once_with(
        repo_path=ANY,
        owner=owner,
        repo=repo,
        scan_result=scan_result,
        base_branch="main",
        remediation_mode=mode,
    )


# ---------------------------------------------------------------------------
# 6.10  Property 4: response contains all required fields
# Validates: Requirements 2.3, 3.4, 5.4
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 4: response contains all required fields
@given(
    created=st.booleans(),
    mode=st.sampled_from(["deterministic", "nondeterministic"]),
)
@settings(max_examples=100)
def test_response_shape(created, mode):
    """Validates: Requirements 2.3, 3.4, 5.4"""
    scan_id = "prop4-test"
    store_scan_result({"scan_id": scan_id, "repository": "owner/repo"})
    mock_inst = MagicMock()
    mock_inst.create_fix_pr.return_value = {
        "created": created,
        "mode": mode,
        "branch": "fix/branch" if created else None,
        "pull_request": {"number": 1} if created else None,
        "reason": None if created else "no issues",
    }
    with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
         patch("app.api.routes.scans.subprocess.run",
               return_value=MagicMock(returncode=0, stderr="")):
        resp = client.post(f"/api/scan/{scan_id}/remediate", json={})
    assert resp.status_code == 200
    body = resp.json()
    for field in ("scan_id", "created", "mode", "branch", "pull_request", "reason"):
        assert field in body, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 6.11  Property 5: owner/repo derived from repository field
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 5: owner/repo derived from repository field
@given(
    owner=st.text(min_size=1, max_size=20,
                  alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"),
                                         whitelist_characters="-_")),
    repo=st.text(min_size=1, max_size=20,
                 alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"),
                                        whitelist_characters="-_")),
)
@settings(max_examples=100, deadline=None)
def test_owner_repo_derived(owner, repo):
    """Validates: Requirements 2.6"""
    scan_id = "prop5-test"
    scan_result = {"scan_id": scan_id, "repository": f"{owner}/{repo}"}
    store_scan_result(scan_result)
    mock_inst = _make_pr_mock()
    with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
         patch("app.api.routes.scans.subprocess.run",
               return_value=MagicMock(returncode=0, stderr="")):
        resp = client.post(f"/api/scan/{scan_id}/remediate", json={})
    assert resp.status_code == 200
    _, kwargs = mock_inst.create_fix_pr.call_args
    assert kwargs["owner"] == owner
    assert kwargs["repo"] == repo


# ---------------------------------------------------------------------------
# 6.12  Property 6: invalid remediation_mode returns 422
# Validates: Requirements 3.5
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 6: invalid remediation_mode returns 422
@given(
    mode=st.text(min_size=1).filter(
        lambda s: s not in ("deterministic", "nondeterministic")
    )
)
@settings(max_examples=100, deadline=None)
def test_invalid_mode_422(mode):
    """Validates: Requirements 3.5"""
    store_scan_result({"scan_id": "prop6-test", "repository": "owner/repo"})
    resp = client.post("/api/scan/prop6-test/remediate",
                       json={"remediation_mode": mode})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6.13  Property 7: PRAgent exception yields HTTP 500
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

# Feature: remediation-api-endpoint, Property 7: PRAgent exception yields HTTP 500
@given(msg=st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_pr_agent_exception_500(msg):
    """Validates: Requirements 3.3"""
    scan_id = "prop7-test"
    store_scan_result({"scan_id": scan_id, "repository": "owner/repo"})
    mock_inst = MagicMock()
    mock_inst.create_fix_pr.side_effect = Exception(msg)
    with patch("app.api.routes.scans.PRAgent", return_value=mock_inst), \
         patch("app.api.routes.scans.subprocess.run",
               return_value=MagicMock(returncode=0, stderr="")):
        resp = client.post(f"/api/scan/{scan_id}/remediate", json={})
    assert resp.status_code == 500
    assert msg in resp.json()["detail"]
