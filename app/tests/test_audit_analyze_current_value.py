"""
Focused test for /api/v1/audit/analyze response fields.

Verifies that issues contain:
  - current_value: actual DB/parser-based current value
  - recommended: empty list [] for now
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_audit_analyze_issues_have_current_value_and_recommended():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={
                "url": "https://www.reddit.com/",
                "max_pages": 5,
                "max_depth": 1,
            },
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    # Top-level issues[] must include current_value and recommended
    issues = data.get("issues", [])
    assert isinstance(issues, list)
    assert len(issues) > 0, "Expected at least one issue"

    for issue in issues:
        assert "current_value" in issue, f"Missing current_value in issue: {issue}"
        assert "recommended" in issue, f"Missing recommended in issue: {issue}"
        assert isinstance(issue["recommended"], list)
        # recommended should be empty per current requirement
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
