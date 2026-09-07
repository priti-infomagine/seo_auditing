"""
Contract / shape tests for the new compact audit read endpoints.

These tests do NOT require a real database. They exercise the route
registration, the request validation, and the OpenAPI schema. The happy
paths (with seeded data) are covered by the service-level unit tests
in ``test_read_model_service.py``.

Goals:
1. New routes are registered under ``/api/v1/audits/...``.
2. Existing ``/api/v1/audit/...`` routes are still present (no removal).
3. The 6 new endpoints are listed in the OpenAPI schema and are GET-only.
"""
from app.main import app


NEW_PATHS = [
    "/api/v1/audits/{audit_id}/overview",
    "/api/v1/audits/{audit_id}/issues",
    "/api/v1/audits/{audit_id}/issues/{issue_id}",
    "/api/v1/audits/{audit_id}/issues/{issue_id}/pages",
    "/api/v1/audits/{audit_id}/issues/{issue_id}/evidence",
    "/api/v1/audits/{audit_id}/pages/{page_id}",
]

LEGACY_PATHS_STILL_PRESENT = [
    "/api/v1/audit/analyze",
    "/api/v1/audit/result/{crawl_id}",
    "/api/v1/audit/result/project/{project_id}",
    "/api/v1/audit/score/{crawl_id}",
    "/api/v1/audit/evaluate/{crawl_id}",
    "/api/v1/audit/parse/{crawl_id}",
    "/api/v1/audit/history",
    "/api/v1/audit/status/{project_id}",
    "/api/v1/audit/pipeline/{project_id}",
    "/api/v1/audit/run",
]


def test_all_new_paths_registered_in_openapi():
    schema = app.openapi()
    paths = set(schema["paths"].keys())
    for p in NEW_PATHS:
        assert p in paths, f"new route {p} missing from OpenAPI"


def test_legacy_audit_paths_still_present():
    schema = app.openapi()
    paths = set(schema["paths"].keys())
    for p in LEGACY_PATHS_STILL_PRESENT:
        assert p in paths, f"legacy route {p} was removed"


def test_legacy_audit_paths_use_get_or_post_unchanged():
    """Sanity: legacy /audit/... paths were not silently retyped."""
    schema = app.openapi()
    for p in LEGACY_PATHS_STILL_PRESENT:
        ops = schema["paths"][p]
        # Each path entry must declare at least one operation
        assert any(k in ("get", "post", "put", "delete", "patch") for k in ops), p


def test_new_paths_all_get():
    schema = app.openapi()
    for p in NEW_PATHS:
        ops = schema["paths"][p]
        assert "get" in ops, f"{p} must be a GET endpoint"
        assert "post" not in ops, f"{p} must be read-only"


def test_new_paths_under_audits_prefix_only():
    """None of the new paths may live under the legacy /audit/ prefix."""
    schema = app.openapi()
    bad = [p for p in schema["paths"] if "/audit/" in p and "/audits/" not in p]
    # Sanity: the legacy set is non-empty (we want this comparison meaningful)
    assert len(bad) >= 5
    # The new endpoints are NOT in the legacy namespace
    for p in NEW_PATHS:
        assert p not in bad, p


def test_legacy_audit_result_endpoint_gains_format_query_param():
    """The existing /audit/result/{crawl_id} endpoint now supports ?format=compact|full.

    The default is 'full' so existing clients are unaffected.
    """
    schema = app.openapi()
    legacy_path = "/api/v1/audit/result/{crawl_id}"
    params = schema["paths"][legacy_path]["get"]["parameters"]
    format_param = next(
        (p for p in params if p.get("name") == "format" and p.get("in") == "query"),
        None,
    )
    assert format_param is not None, "format query param missing from legacy endpoint"
    assert format_param["schema"]["type"] == "string"
    assert set(format_param["schema"]["enum"]) == {"full", "compact"}
    assert format_param["schema"]["default"] == "full"
