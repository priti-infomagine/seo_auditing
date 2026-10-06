from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.database import Base
from app.modules.seprate_checks.backlink_analysis.model import (
    BacklinkCheckStatus,
)
from app.modules.seprate_checks.backlink_analysis.router import router
from app.modules.seprate_checks.backlink_analysis.schema import BacklinkCheckRequest
from app.modules.seprate_checks.backlink_analysis.service import (
    BacklinkAnalysisService,
    DataForSEOConfigurationError,
)


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        pass

    async def refresh(self, _item):
        assert _item is not None

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_run_check_persists_provider_result(monkeypatch):
    result = [
        {
            "data": {
                "target": "example.com",
                "rank": 10,
                "backlinks": 20,
                "referringDomains": 5,
                "referringMainDomains": 4,
                "spamScore": 1,
                "brokenBacklinks": 0,
                "referringPages": 15,
            },
            "cost": 0.024036,
            "evidence": {},
        }
    ]
    client = SimpleNamespace(get_backlink_summary=AsyncMock(return_value=result))
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service.settings.DATAFORSEO_LOGIN",
        "login",
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service.settings.DATAFORSEO_PASSWORD",
        "password",
    )
    def fake_client_factory(login, password):
        assert login == "login"
        assert password == "password"
        return client

    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service.DataForSEOClient",
        fake_client_factory,
    )
    db = FakeSession()

    check = await BacklinkAnalysisService.run_check("example.com", 50, db)

    assert check.status == BacklinkCheckStatus.COMPLETED.value
    assert check.result == result
    assert check.cost == 0.024036
    assert check.evidence_limit == 50
    assert db.commits == 2
    client.get_backlink_summary.assert_awaited_once_with("example.com", 50)


@pytest.mark.asyncio
async def test_run_check_persists_failed_status_and_surfaces_missing_credentials(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service.settings.DATAFORSEO_LOGIN",
        "",
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service.settings.DATAFORSEO_PASSWORD",
        "",
    )
    db = FakeSession()

    with pytest.raises(DataForSEOConfigurationError):
        await BacklinkAnalysisService.run_check("example.com", 100, db)

    check = db.added[0]
    assert check.status == BacklinkCheckStatus.FAILED.value
    assert check.error == "DataForSEO credentials are not configured"
    assert db.commits == 2


def test_backlink_api_schemas_normalize_target_and_router_is_registered():
    request = BacklinkCheckRequest(target="https://www.example.com/path")

    from app.main import app

    assert request.target == "example.com"
    assert {
        (route.path, tuple(sorted(route.methods or [])))
        for route in router.routes
    } >= {
        ("/check", ("POST",)),
        ("/checks", ("GET",)),
        ("/checks/{check_id}", ("GET",)),
    }
    assert "backlink_checks" in Base.metadata.tables
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/backlinks/check"]
    assert "get" in paths["/api/v1/backlinks/checks"]
    assert "get" in paths["/api/v1/backlinks/checks/{check_id}"]
    post_response = paths["/api/v1/backlinks/check"]["post"]["responses"]["201"]
    assert post_response["content"]["application/json"]["schema"]["type"] == "array"
