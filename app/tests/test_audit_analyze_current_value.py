"""
Focused test for /api/v1/audit/analyze response fields (async / queued flow).

Verifies that issues contain:
  - current_value: actual DB/parser-based current value
  - recommended: empty list [] for now

The crawl is simulated offline (seeded rows) and the real pipeline is run
against the same Postgres database; Celery broker/backend are bypassed.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tests.test_audit_analyze import (
    mock_celery,
    _seed_crawl,
    _run_pipeline,
    _poll_task_until_terminal,
)


@pytest.mark.asyncio
async def test_audit_analyze_issues_have_current_value_and_recommended(
    mock_celery, _ensure_schema
):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert response.status_code == 202, response.text
        posted = response.json()
        audit_id = uuid.UUID(posted["audit_id"])
        audit_id = uuid.UUID(posted["audit_id"])
        task_id = posted["task_id"]

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, audit_id, n_pages=2)

        await _run_pipeline(audit_id, audit_id, session_factory)

        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{audit_id}?audit_id={audit_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    # Top-level issues[] must include occurrences with current_value
    issues = data.get("issues", [])
    assert isinstance(issues, list)
    assert len(issues) > 0, "Expected at least one issue"
    for issue in issues:
        assert "recommendation" in issue, f"Missing recommendation in issue: {issue}"
        for occ in issue.get("occurrences", []):
            assert "current_value" in occ, f"Missing current_value in occurrence: {occ}"

    # Verify current_value is a non-empty string for at least one failed issue occurrence
    assert any(
        isinstance(occ.get("current_value"), str) and occ["current_value"]
        for i in issues
        for occ in i.get("occurrences", [])
    ), "Expected at least one issue occurrence to have a non-empty current_value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
