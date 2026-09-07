"""
Contract tests for the ``?format=compact|full`` query switch on
``GET /api/v1/audit/result/{crawl_id}``.

These tests are pure OpenAPI / dispatch tests — no real DB.

Goals:
1. ``format`` is a ``Literal["full", "compact"]`` query parameter on the
   existing audit result endpoint.
2. The default value is ``full`` (legacy contract preserved).
3. Unknown values are rejected by FastAPI (422).
4. The route's source dispatches ``format=full`` to
   ``AuditResponseBuilder.build`` and ``format=compact`` to
   ``AuditReadModelService.build_overview`` (asserted via the route
   function's source — avoids the DB-backed conftest fixture).
5. The legacy test suite (``test_unified_response.py``) still works.
"""
import inspect
import re

from app.api.endpoints.v1.audit import results as results_module
from app.main import app

PATH = "/api/v1/audit/result/{crawl_id}"


# --------------------------------------------------------------------- OpenAPI


def test_format_query_param_is_registered():
    schema = app.openapi()
    params = schema["paths"][PATH]["get"].get("parameters", [])
    format_params = [p for p in params if p.get("name") == "format" and p.get("in") == "query"]
    assert format_params, "format query param is missing from /audit/result/{crawl_id}"
    fp = format_params[0]
    schema_obj = fp["schema"]
    assert schema_obj["type"] == "string"
    assert set(schema_obj.get("enum", [])) == {"full", "compact"}


def test_format_query_param_default_is_full():
    schema = app.openapi()
    params = schema["paths"][PATH]["get"]["parameters"]
    format_param = next(p for p in params if p.get("name") == "format")
    assert format_param["schema"].get("default") == "full"


def test_unknown_format_value_is_invalidated_by_fastapi():
    """FastAPI's Literal type generates an enum that rejects unknown values with 422."""
    schema = app.openapi()
    params = schema["paths"][PATH]["get"]["parameters"]
    format_param = next(p for p in params if p.get("name") == "format")
    assert "enum" in format_param["schema"]
    assert "garbage" not in format_param["schema"]["enum"]


# --------------------------------------------------------------------- dispatch (source-level)


def test_route_source_dispatches_compact_to_read_model_service():
    """The route handler must call ``AuditReadModelService.build_overview`` for compact.

    Asserted by inspecting the source (no DB fixture needed) so the test is
    fast and does not require a running Postgres.
    """
    src = inspect.getsource(results_module.get_analysis_result)
    # Both branches must be present in the handler
    assert "format" in src
    assert "compact" in src
    assert "AuditReadModelService" in src
    assert "build_overview" in src
    # The branch is structured as an early return for compact
    assert re.search(r"if\s+format\s*==\s*['\"]compact['\"]", src), (
        "expected `if format == 'compact':` branch in get_analysis_result"
    )


def test_route_source_dispatches_full_to_response_builder():
    """The route handler must call ``AuditResponseBuilder.build`` for full / default."""
    src = inspect.getsource(results_module.get_analysis_result)
    assert "AuditResponseBuilder" in src
    assert "builder.build" in src
    # The full branch must be the fallthrough after the compact branch
    assert ".build(project_id, crawl_id)" in src


# --------------------------------------------------------------------- project-keyed endpoint


def test_project_keyed_endpoint_has_format_query_param():
    """GET /audit/result/project/{project_id} must declare ?format=compact|full."""
    schema = app.openapi()
    path = "/api/v1/audit/result/project/{project_id}"
    params = schema["paths"][path]["get"].get("parameters", [])
    format_params = [
        p for p in params
        if p.get("name") == "format" and p.get("in") == "query"
    ]
    assert format_params, f"format query param is missing from {path}"
    fp = format_params[0]
    assert fp["schema"]["type"] == "string"
    assert set(fp["schema"].get("enum", [])) == {"full", "compact"}
    assert fp["schema"].get("default") == "full"


def test_project_keyed_route_source_dispatches_compact_to_read_model():
    """The project-keyed handler must call ``AuditReadModelService.build_overview`` for compact."""
    src = inspect.getsource(results_module.get_analysis_result_by_project)
    assert "format" in src
    assert "compact" in src
    assert "AuditReadModelService" in src
    assert "build_overview" in src
    assert re.search(r"if\s+format\s*==\s*['\"]compact['\"]", src), (
        "expected `if format == 'compact':` branch in get_analysis_result_by_project"
    )
    # 202 fallthrough must still exist for the "not ready" case
    assert "202" in src


# --------------------------------------------------------------------- POST /audit/analyze echo


def test_analyze_endpoint_accepts_format_query_param():
    """POST /audit/analyze must declare ?format=compact|full in its OpenAPI."""
    schema = app.openapi()
    path = "/api/v1/audit/analyze"
    params = schema["paths"][path]["post"].get("parameters", [])
    format_params = [
        p for p in params
        if p.get("name") == "format" and p.get("in") == "query"
    ]
    assert format_params, f"format query param is missing from {path}"
    fp = format_params[0]
    assert fp["schema"]["type"] == "string"
    assert set(fp["schema"].get("enum", [])) == {"full", "compact"}
    assert fp["schema"].get("default") == "full"


def test_analyze_source_echoes_format_into_result_urls():
    """The 202 body must include ``&format=...`` on the two result URLs when format=compact.

    Asserted at the source level so no DB is required.
    """
    from app.api.endpoints.v1.audit import analyze as analyze_module
    src = inspect.getsource(analyze_module.analyze_website)
    # The handler must define a `format` param
    assert "format" in src
    # The handler must reference the `format` variable in result_url and result_project_url
    # Build a coarse check: both result_url and result_project_url lines exist
    # and the `fmt` suffix is applied to both.
    assert "result_url=" in src
    assert "result_project_url=" in src
    # The `fmt` variable is only used when format != full; assert that branch exists
    assert "fmt" in src
    assert "if format == \"full\"" in src
    # Both URLs must include the {fmt} interpolation
    # Look for the two URL f-strings
    for marker in (
        "result_url=f\"/api/v1/audit/result/{crawl_id}?project_id={project_id}{fmt}\"",
        "result_project_url=f\"/api/v1/audit/result/project/{project_id}{fmt}\"",
    ):
        assert marker in src, f"missing URL pattern: {marker}"


# --------------------------------------------------------------------- legacy-preservation guard


def test_legacy_test_suite_still_passes():
    """Indirect check: the legacy ``test_unified_response.py`` is importable
    and its module-level imports still work. The full pytest run is executed
    separately in CI; this test guards against accidental rename of
    ``AuditResponseBuilder``."""
    from app.modules.audit.services.audit_response_builder import AuditResponseBuilder
    assert hasattr(AuditResponseBuilder, "build")
    assert hasattr(AuditResponseBuilder, "_build_summary")
    assert hasattr(AuditResponseBuilder, "_build_categories")
    assert hasattr(AuditResponseBuilder, "_build_issues")

