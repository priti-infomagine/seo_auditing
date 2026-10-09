import asyncio

from app.modules.streaming_audit.models.streaming_page_result import StreamingPageResult
from app.modules.streaming_audit.services.page_scheduler import PageScheduler
from app.modules.streaming_audit.services.streaming_audit_service import dedupe_urls, normalize_url
from app.modules.streaming_audit.services.page_processor import PageProcessor
from app.modules.streaming_audit.tasks import _run_on_worker_loop


def test_normalize_url_removes_trailing_slash_and_fragment():
    assert normalize_url("https://example.com/path/?a=1#fragment") == "https://example.com/path?a=1"


def test_dedupe_urls_ignores_duplicate_variants():
    urls = [
        "https://example.com/about",
        "https://example.com/about/",
        "https://example.com/about#top",
        "https://example.com/contact",
    ]
    assert dedupe_urls(urls) == [
        "https://example.com/about",
        "https://example.com/contact",
    ]


def test_page_scheduler_respects_max_depth_and_limit():
    scheduler = PageScheduler(max_pages=2, max_depth=1)
    scheduled = scheduler.schedule_batch([
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/contact",
        "https://example.com/ignored",
    ], depth=1)
    assert len(scheduled) <= 2
    assert all(url.startswith("https://example.com") for url in scheduled)


def test_page_scheduler_fanout_respects_active_capacity():
    scheduler = PageScheduler(max_pages=10, max_depth=2)
    scheduled = scheduler.schedule_fanout(
        [
            "https://example.com/about",
            "https://example.com/contact",
            "https://example.com/pricing",
            "https://example.com/about#top",
        ],
        depth=1,
        active_slots=8,
        concurrency_limit=10,
    )
    assert len(scheduled) == 2
    assert scheduled == [
        "https://example.com/about",
        "https://example.com/contact",
    ]


def test_page_result_has_database_dedupe_constraint():
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in StreamingPageResult.__table__.constraints
        if constraint.name == "uq_streaming_page_result_audit_url"
    }
    assert constraints == {
        "uq_streaming_page_result_audit_url": ("audit_id", "normalized_url"),
    }


def test_worker_tasks_reuse_one_event_loop():
    async def current_loop_id():
        return id(asyncio.get_running_loop())

    assert _run_on_worker_loop(current_loop_id()) == _run_on_worker_loop(current_loop_id())


def test_page_processor_resolves_discovered_paths_against_final_domain():
    class FakeCrawler:
        async def fetch_page(self, _url):
            return {
                "status": "ok",
                "html": "<html></html>",
                "final_url": "https://example.com/services/",
                "status_code": 200,
            }

    class FakeParser:
        def parse_html(self, _html, url, _fetch_result):
            assert url == "https://example.com/services/"
            return {
                "links": [
                    {"href": "/services/it-consulting-services"},
                    {"href": "about"},
                    {"href": "//cdn.example.com/asset"},
                    {"href": "mailto:info@example.com"},
                    {"href": "javascript:void(0)"},
                ]
            }

    class FakeRuleEngine:
        async def evaluate(self, _parsed_data):
            return {"overall_score": 80}

    result = asyncio.run(
        PageProcessor(FakeCrawler(), FakeParser(), FakeRuleEngine()).process_page(
            "audit-id",
            "https://example.com/old-path",
        )
    )

    assert result["discovered_urls"] == [
        "https://example.com/services/it-consulting-services",
        "https://example.com/services/about",
        "https://cdn.example.com/asset",
    ]
