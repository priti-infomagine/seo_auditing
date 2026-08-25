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
        crawl_id = uuid.UUID(posted["crawl_id"])
        project_id = uuid.UUID(posted["project_id"])
        task_id = posted["task_id"]

        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)

        await _run_pipeline(crawl_id, project_id, session_factory)

        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{crawl_id}?project_id={project_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    # Top-level issues[] must include current_value and recommended
    issues = data.get("issues", [])
    assert isinstance(issues, list)
    assert len(issues) > 0, "Expected at least one issue"
    for issue in issues:
        assert "current_value" in issue, f"Missing current_value in issue: {issue}"
        assert "recommended" in issue, f"Missing recommended in issue: {issue}"
        assert isinstance(issue["recommended"], list)
        assert issue["recommended"] == []

    # categories[].issues[] must also include current_value and recommended
    categories = data.get("categories", [])
    category_issues_found = False
    for category in categories:
        cat_issues = category.get("issues", [])
        if not cat_issues:
            continue
        category_issues_found = True
        for issue in cat_issues:
            assert "current_value" in issue, (
                f"Missing current_value in category issue for {category['id']}: {issue}"
            )
            assert "recommended" in issue, (
                f"Missing recommended in category issue for {category['id']}: {issue}"
            )
            assert isinstance(issue["recommended"], list)
            assert issue["recommended"] == []

    assert category_issues_found, "Expected at least one category to have issues"

    # Verify current_value is a non-empty string for at least one failed issue
    assert any(
        isinstance(i.get("current_value"), str) and i["current_value"]
        for i in issues
    ), "Expected at least one issue to have a non-empty current_value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
