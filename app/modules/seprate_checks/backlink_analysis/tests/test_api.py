from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.database import Base
from app.modules.seprate_checks.backlink_analysis.model import (
    BacklinkCheckStatus,
)
from app.modules.seprate_checks.backlink_analysis.router import _to_response, router
from app.modules.seprate_checks.backlink_analysis.schema import (
    BacklinkCheckRequest,
    BacklinkReport,
)
from app.modules.seprate_checks.backlink_analysis.service import (
    BacklinkAnalysisService,
    DataForSEOConfigurationError,
    close_dataforseo_client,
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
    result = {
        "domain": "example.com",
        "domainRank": 10,
        "backlinks": 20,
        "referringDomains": 5,
        "referringMainDomains": 4,
        "referringPages": 15,
        "brokenBacklinks": 0,
        "backlinksSpamScore": 2,
        "cost": 0.01,
        "evidence": {
            "referringPages": ["https://source.example/a"],
            "brokenBacklinks": [],
        },
    }
    client = SimpleNamespace(get_backlink_summary=AsyncMock(return_value=result))
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service._dataforseo_client",
        None,
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service._dataforseo_credentials",
        None,
    )
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

    check = await BacklinkAnalysisService.run_check("example.com", db)

    assert check.status == BacklinkCheckStatus.COMPLETED.value
    assert check.result == result
    assert check.cost == 0.01
    assert check.evidence_limit == 100
    assert db.commits == 2
    client.get_backlink_summary.assert_awaited_once_with("example.com")


@pytest.mark.asyncio
async def test_run_check_persists_failed_status_and_surfaces_missing_credentials(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service._dataforseo_client",
        None,
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service._dataforseo_credentials",
        None,
    )
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
        await BacklinkAnalysisService.run_check("example.com", db)

    check = db.added[0]
    assert check.status == BacklinkCheckStatus.FAILED.value
    assert check.error == "DataForSEO credentials are not configured"
    assert db.commits == 2


@pytest.mark.asyncio
async def test_close_dataforseo_client_closes_and_resets_shared_client(monkeypatch):
    client = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service._dataforseo_client",
        client,
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.service._dataforseo_credentials",
        ("login", "password"),
    )

    await close_dataforseo_client()

    client.aclose.assert_awaited_once()


def test_to_response_converts_legacy_single_item_report():
    check = SimpleNamespace(
        id=uuid4(),
        target="example.com",
        status=BacklinkCheckStatus.COMPLETED.value,
        result=[
            {
                "data": {
                    "target": "example.com",
                    "rank": 12,
                    "backlinks": 34,
                    "referringDomains": 5,
                    "referringPages": 21,
                    "brokenBacklinks": 2,
                    "spamScore": 10,
                },
                "cost": 0.02,
                "evidence": {
                    "referringPages": [
                        "https://source.example/old-a",
                        "https://source.example/old-b",
                    ],
                    "brokenBacklinks": ["https://broken.example/old"],
                },
            }
        ],
        cost=0.02,
        error=None,
        created_at=None,
        updated_at=None,
    )

    result = _to_response(check)

    assert result.result is not None
    assert result.result.domain == "example.com"
    assert result.result.domainRank == 12
    assert result.result.backlinks == 34
    assert result.result.brokenBacklinks == 2
    assert result.result.backlinksSpamScore is None
    assert result.result.evidence.referringPages == [
        "https://source.example/old-a",
        "https://source.example/old-b",
    ]
    assert result.result.evidence.brokenBacklinks == [
        "https://broken.example/old"
    ]
    assert result.error is None


def test_to_response_reports_bad_result_without_raising():
    checks = [
        SimpleNamespace(
            id=uuid4(),
            target="example.com",
            status=BacklinkCheckStatus.COMPLETED.value,
            result=[{"unexpected": "shape"}],
            cost=0.02,
            error=None,
            created_at=None,
            updated_at=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            target="other.example",
            status=BacklinkCheckStatus.COMPLETED.value,
            result={
                "domain": "other.example",
                "evidence": {
                    "referringPages": [
                        f"https://source{i}.example/page" for i in range(1, 8)
                    ],
                    "brokenBacklinks": ["https://broken.example/page"],
                },
            },
            cost=0.01,
            error=None,
            created_at=None,
            updated_at=None,
        ),
    ]

    results = [_to_response(check) for check in checks]

    assert len(results) == 2
    assert results[0].result is None
    assert results[0].error == "Stored backlink result has an unsupported format"
    assert results[1].result is not None
    assert results[1].result.domain == "other.example"
    assert results[1].result.evidence.referringPages == [
        f"https://source{i}.example/page" for i in range(1, 6)
    ]
    assert results[1].result.evidence.brokenBacklinks == [
        "https://broken.example/page"
    ]


def test_backlink_api_schemas_normalize_target_and_router_is_registered():
    request = BacklinkCheckRequest(target="https://www.example.com/path")
    report = BacklinkReport(
        domain="example.com",
        backlinksSpamScore=11,
        evidence={
            "referringPages": ["https://source.example/a"],
            "brokenBacklinks": ["https://broken.example/a"],
        },
    )

    from app.main import app

    assert request.target == "example.com"
    assert set(report.model_dump()) == {
        "domain",
        "domainRank",
        "backlinks",
        "referringDomains",
        "referringMainDomains",
        "referringPages",
        "brokenBacklinks",
        "backlinksSpamScore",
        "cost",
        "evidence",
    }
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
    post_response = paths["/api/v1/backlinks/check"]["post"]["responses"]["200"]
    assert post_response["content"]["application/json"]["schema"]["$ref"].endswith(
        "/BacklinkReport"
    )
    check_route = next(route for route in router.routes if route.path == "/check")
    assert check_route.status_code == 200
