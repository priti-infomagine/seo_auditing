from unittest.mock import AsyncMock

import pytest

from app.modules.seprate_checks.backlink_analysis.data_for_seo_client import (
    DataForSEOClient,
)


@pytest.mark.asyncio
async def test_get_backlink_summary_returns_metrics_cost_and_per_metric_evidence(
    monkeypatch,
):
    summary_response = {
        "status_code": 20000,
        "cost": 0.01,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "infomagine.in",
                        "rank": 108,
                        "backlinks": 139,
                        "referring_domains": 58,
                        "referring_main_domains": 57,
                        "broken_backlinks": 1,
                        "referring_pages": 96,
                        "info": {"target_spam_score": 24},
                    }
                ],
            }
        ],
    }
    evidence_response = {
        "status_code": 20000,
        "cost": 0.014036,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "url_from": "https://referrer.example/page-a",
                                "domain_from": "referrer.example",
                                "is_broken": False,
                            },
                            {
                                "url_from": "https://referrer.example/page-b",
                                "domain_from": "referrer.example",
                                "is_broken": True,
                            },
                            {
                                "url_from": "https://another.example/page",
                                "domain_from": "another.example",
                                "is_broken": False,
                            },
                        ]
                    }
                ],
            }
        ],
    }
    client = DataForSEOClient("login", "password")
    monkeypatch.setattr(
        client,
        "_post",
        AsyncMock(side_effect=[summary_response, evidence_response]),
    )

    report = await client.get_backlink_summary("infomagine.in", limit=10)

    assert report == [
        {
            "data": {
                "target": "infomagine.in",
                "rank": 108,
                "backlinks": 139,
                "referringDomains": 58,
                "referringMainDomains": 57,
                "spamScore": 24,
                "brokenBacklinks": 1,
                "referringPages": 96,
            },
            "cost": 0.024036,
            "evidence": {
                "rank": [
                    "https://referrer.example/page-a",
                    "https://referrer.example/page-b",
                    "https://another.example/page",
                ],
                "backlinks": [
                    "https://referrer.example/page-a",
                    "https://referrer.example/page-b",
                    "https://another.example/page",
                ],
                "referringDomains": [
                    "https://referrer.example/page-a",
                    "https://another.example/page",
                ],
                "referringMainDomains": [
                    "https://referrer.example/page-a",
                    "https://another.example/page",
                ],
                "spamScore": [
                    "https://referrer.example/page-a",
                    "https://referrer.example/page-b",
                    "https://another.example/page",
                ],
                "brokenBacklinks": ["https://referrer.example/page-b"],
                "referringPages": [
                    "https://referrer.example/page-a",
                    "https://referrer.example/page-b",
                    "https://another.example/page",
                ],
            },
        }
    ]


@pytest.mark.asyncio
async def test_get_backlink_summary_rejects_provider_task_errors(monkeypatch):
    client = DataForSEOClient("login", "password")
    monkeypatch.setattr(
        client,
        "_post",
        AsyncMock(
            return_value={
                "status_code": 20000,
                "cost": 0,
                "tasks": [
                    {
                        "status_code": 40501,
                        "status_message": "Invalid target",
                        "result": [],
                    }
                ],
            }
        ),
    )

    with pytest.raises(RuntimeError, match="Invalid target"):
        await client.get_backlink_summary("not-a-domain")


@pytest.mark.asyncio
async def test_get_backlink_summary_validates_evidence_limit():
    client = DataForSEOClient("login", "password")

    with pytest.raises(ValueError, match="limit must be between"):
        await client.get_backlink_summary("infomagine.in", limit=0)
