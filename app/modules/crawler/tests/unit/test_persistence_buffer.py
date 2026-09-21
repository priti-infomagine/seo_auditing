"""
Unit tests for CrawlPersistenceService buffering and bulk-flush logic.

Covers:
  - Auto-flush at flush_every threshold (network, seo, resources, links)
  - Independent per-buffer flushing
  - flush_all() flushes all non-empty buffers
  - flush_all() is fault-tolerant (one buffer failure doesn't block others)
  - ON CONFLICT upsert for SEO/network (statement-level verification)
  - set_flush_every() changes the threshold
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.modules.crawler.services.crawl_persistence_service import CrawlPersistenceService
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_resources import PageResource
from app.modules.crawler.models.page_links import PageLink
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _make_mock_db():
    """Create a mock async session with the methods used by the persistence service."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_service(db=None, flush_every=20):
    db = db or _make_mock_db()
    return CrawlPersistenceService(db=db, crawl_job_id=uuid4(), flush_every=flush_every), db


def _make_network_data(page_id=None):
    return PageNetworkData(
        page_id=page_id or uuid4(),
        status_code=200,
        content_type="text/html",
        content_length=1024,
        response_time_ms=50,
        headers={"content-type": "text/html"},
        redirects=[],
        security={},
        performance={},
    )


def _make_seo_data(page_id=None):
    return PageSEOData(
        page_id=page_id or uuid4(),
        title="Test Title",
        title_length=10,
        meta_description="desc",
        meta_description_length=4,
        canonical="https://example.com",
        robots_meta="index,follow",
        language="en",
        charset="utf-8",
        viewport="width=device-width",
        favicon="/favicon.ico",
        word_count=100,
        content_hash="abc123",
        headings={"h1": 1, "h2": 2},
        content={"text": "hello world"},
        structured_data={},
        social={},
        indexability={},
        accessibility={},
    )


class TestBufferAutoFlush:
    """Verify each buffer auto-flushes when reaching the flush_every threshold."""

    async def test_buffer_network_auto_flushes_at_threshold(self):
        service, db = _make_service(flush_every=3)
        for i in range(3):
            await service.buffer_network(_make_network_data())
        assert len(service._buf_network) == 0
        assert db.execute.call_count >= 1
        assert db.flush.call_count >= 1

    async def test_buffer_seo_auto_flushes_at_threshold(self):
        service, db = _make_service(flush_every=3)
        for i in range(3):
            await service.buffer_seo(_make_seo_data())
        assert len(service._buf_seo) == 0
        assert db.execute.call_count >= 1
        assert db.flush.call_count >= 1

    async def test_buffer_resources_auto_flushes_at_threshold(self):
        service, db = _make_service(flush_every=3)
        page_id = uuid4()
        for i in range(3):
            await service.buffer_resources(
                page_id, [{"url": f"https://example.com/r{i}", "type": "image"}]
            )
        assert len(service._buf_resources) == 0
        assert db.add_all.call_count >= 1
        assert db.flush.call_count >= 1

    async def test_buffer_links_auto_flushes_at_threshold(self):
        service, db = _make_service(flush_every=3)
        page_id = uuid4()
        for i in range(3):
            await service.buffer_links(
                page_id, [{"url": f"https://example.com/l{i}"}]
            )
        assert len(service._buf_links) == 0
        assert db.add_all.call_count >= 1
        assert db.flush.call_count >= 1

    async def test_no_flush_below_threshold(self):
        service, db = _make_service(flush_every=20)
        for i in range(19):
            await service.buffer_network(_make_network_data())
        assert len(service._buf_network) == 19
        assert db.execute.call_count == 0


class TestIndependentBuffers:
    """Verify buffers flush independently — one at threshold doesn't affect others."""

    async def test_buffers_flush_independently(self):
        service, db = _make_service(flush_every=3)

        # Buffer 3 resources (triggers flush) — network/seo buffers should be untouched
        page_id = uuid4()
        for i in range(3):
            await service.buffer_resources(
                page_id, [{"url": f"https://example.com/r{i}", "type": "script"}]
            )
        assert len(service._buf_resources) == 0
        assert len(service._buf_network) == 0
        assert len(service._buf_seo) == 0

        # Buffer 2 network items (below threshold) — no flush yet
        for i in range(2):
            await service.buffer_network(_make_network_data())
        assert len(service._buf_network) == 2

        # Buffer 3 seo items (triggers flush) — network buffer should still have 2 items
        for i in range(3):
            await service.buffer_seo(_make_seo_data())
        assert len(service._buf_seo) == 0
        assert len(service._buf_network) == 2


class TestFlushAll:
    """Verify flush_all() flushes all non-empty buffers."""

    async def test_flush_all_flushes_partial_buffers(self):
        service, db = _make_service(flush_every=20)

        # Add items below threshold to each buffer
        for i in range(5):
            await service.buffer_network(_make_network_data())
        for i in range(3):
            await service.buffer_seo(_make_seo_data())
        page_id = uuid4()
        for i in range(4):
            await service.buffer_resources(
                page_id, [{"url": f"https://example.com/r{i}", "type": "image"}]
            )
        for i in range(2):
            await service.buffer_links(page_id, [{"url": f"https://example.com/l{i}"}])

        assert len(service._buf_network) == 5
        assert len(service._buf_seo) == 3
        assert len(service._buf_resources) == 4
        assert len(service._buf_links) == 2

        await service.flush_all()

        assert len(service._buf_network) == 0
        assert len(service._buf_seo) == 0
        assert len(service._buf_resources) == 0
        assert len(service._buf_links) == 0
        assert db.execute.call_count >= 2  # network + seo use execute
        assert db.add_all.call_count >= 2  # resources + links use add_all

    async def test_flush_all_on_empty_buffers_is_noop(self):
        service, db = _make_service(flush_every=20)
        await service.flush_all()
        assert db.execute.call_count == 0
        assert db.add_all.call_count == 0

    async def test_flush_all_continues_on_per_buffer_failure(self):
        service, db = _make_service(flush_every=20)

        # Populate all buffers below threshold
        await service.buffer_network(_make_network_data())
        await service.buffer_seo(_make_seo_data())
        page_id = uuid4()
        await service.buffer_resources(page_id, [{"url": "https://example.com/r", "type": "image"}])
        await service.buffer_links(page_id, [{"url": "https://example.com/l"}])

        # Make _flush_network_locked raise — it should be caught in flush_all
        original_flush_network = service._flush_network_locked

        async def failing_flush_network():
            raise RuntimeError("network flush failed")

        service._flush_network_locked = failing_flush_network

        await service.flush_all()

        # network buffer preserved (flush failed), others cleared
        assert len(service._buf_network) == 1  # preserved because flush failed
        assert len(service._buf_seo) == 0       # cleared successfully
        assert len(service._buf_resources) == 0  # cleared successfully
        assert len(service._buf_links) == 0     # cleared successfully

        # Restore
        service._flush_network_locked = original_flush_network


class TestUpsertPattern:
    """Verify the pg_insert().on_conflict_do_update pattern is used for SEO/network."""

    async def test_flush_seo_uses_pg_insert_with_on_conflict(self):
        service, db = _make_service(flush_every=2)
        seo_data = _make_seo_data()
        await service.buffer_seo(seo_data)
        await service.buffer_seo(_make_seo_data())

        # db.execute should have been called with an Insert statement
        assert db.execute.call_count >= 1
        stmt = db.execute.call_args.args[0]

        # Verify it's a postgresql insert with on_conflict set
        from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate
        assert stmt._post_values_clause is not None
        assert isinstance(stmt._post_values_clause, OnConflictDoUpdate)
        assert "page_id" in stmt._post_values_clause.inferred_target_elements

    async def test_flush_network_uses_pg_insert_with_on_conflict(self):
        service, db = _make_service(flush_every=2)
        await service.buffer_network(_make_network_data())
        await service.buffer_network(_make_network_data())

        assert db.execute.call_count >= 1
        stmt = db.execute.call_args.args[0]

        from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate
        assert stmt._post_values_clause is not None
        assert isinstance(stmt._post_values_clause, OnConflictDoUpdate)
        assert "page_id" in stmt._post_values_clause.inferred_target_elements

    async def test_flush_resources_uses_add_all(self):
        service, db = _make_service(flush_every=1)
        page_id = uuid4()
        await service.buffer_resources(page_id, [{"url": "https://example.com/r", "type": "image"}])

        assert db.add_all.call_count >= 1
        assert db.flush.call_count >= 1

    async def test_flush_links_uses_add_all(self):
        service, db = _make_service(flush_every=1)
        page_id = uuid4()
        await service.buffer_links(page_id, [{"url": "https://example.com/l"}])

        assert db.add_all.call_count >= 1
        assert db.flush.call_count >= 1


class TestSetFlushEvery:
    """Verify set_flush_every() changes the threshold."""

    async def test_set_flush_every_changes_threshold(self):
        service, db = _make_service(flush_every=20)
        assert service._flush_every == 20

        service.set_flush_every(5)
        assert service._flush_every == 5

        # Now threshold is 5
        for i in range(5):
            await service.buffer_network(_make_network_data())
        assert len(service._buf_network) == 0

    async def test_set_flush_every_lower_threshold(self):
        service, db = _make_service(flush_every=20)

        for i in range(2):
            await service.buffer_network(_make_network_data())
        assert len(service._buf_network) == 2  # below 20, no flush

        service.set_flush_every(2)
        await service.buffer_network(_make_network_data())
        assert len(service._buf_network) == 0  # now threshold is 2, and we have 3 total


class TestBuildHelpers:
    """Verify the extracted construction helpers preserve the original logic."""

    def test_build_resource_objects_preserves_url_as_normalized(self):
        service, db = _make_service()
        page_id = uuid4()
        resources = [
            {"url": "https://example.com/img.jpg", "type": "image", "alt": "alt text",
             "width": "800", "height": "600", "status_code": 200, "size_bytes": 1024},
        ]
        objs = service._build_resource_objects(page_id, resources, page_url="https://example.com")

        assert len(objs) == 1
        obj = objs[0]
        assert obj.page_id == page_id
        assert obj.url == "https://example.com/img.jpg"
        assert obj.normalized_url == "https://example.com/img.jpg"  # same as url
        assert obj.alt == "alt text"
        assert obj.width == 800
        assert obj.height == 600
        assert obj.status_code == 200
        assert obj.size_bytes == 1024
        assert obj.is_mixed_content is False  # https on https page

    def test_build_resource_objects_detects_mixed_content(self):
        service, db = _make_service()
        page_id = uuid4()
        resources = [
            {"url": "http://example.com/insecure.jpg", "type": "image"},
        ]
        objs = service._build_resource_objects(page_id, resources, page_url="https://example.com")
        assert objs[0].is_mixed_content is True

    def test_build_resource_objects_handles_non_dict(self):
        service, db = _make_service()
        page_id = uuid4()
        resources = [None, "not a dict", {"url": "https://example.com/ok.jpg", "type": "image"}]
        objs = service._build_resource_objects(page_id, resources)
        assert len(objs) == 1

    def test_build_resource_objects_coerces_invalid_ints(self):
        service, db = _make_service()
        page_id = uuid4()
        resources = [{"url": "https://example.com/img.jpg", "width": "not_a_number"}]
        objs = service._build_resource_objects(page_id, resources)
        assert objs[0].width is None

    def test_build_link_objects_preserves_all_fields(self):
        service, db = _make_service()
        page_id = uuid4()
        links = [
            {
                "url": "https://example.com/page",
                "anchor_text": "Click here",
                "rel": "nofollow",
                "link_type": "anchor",
                "is_internal": True,
                "is_external": False,
                "nofollow": True,
                "ugc": False,
                "sponsored": False,
            }
        ]
        objs = service._build_link_objects(page_id, links)

        assert len(objs) == 1
        obj = objs[0]
        assert obj.page_id == page_id
        assert obj.crawl_job_id == service.crawl_job_id
        assert obj.target_url == "https://example.com/page"
        assert obj.normalized_target_url == "https://example.com/page"  # same as url
        assert obj.anchor_text == "Click here"
        assert obj.rel == "nofollow"
        assert obj.link_type == "anchor"
        assert obj.is_internal is True
        assert obj.is_external is False
        assert obj.nofollow is True
        assert obj.ugc is False
        assert obj.sponsored is False
        assert obj.is_crawlable is True  # = is_internal

    def test_build_link_objects_uses_defaults(self):
        service, db = _make_service()
        page_id = uuid4()
        links = [{"url": "https://example.com/page"}]
        objs = service._build_link_objects(page_id, links)

        assert len(objs) == 1
        obj = objs[0]
        assert obj.link_type == "anchor"
        assert obj.is_internal is True
        assert obj.is_external is False
        assert obj.nofollow is False
        assert obj.is_crawlable is True

    def test_build_link_objects_skips_non_dict(self):
        service, db = _make_service()
        page_id = uuid4()
        links = [None, "junk", {"url": "https://example.com/ok"}]
        objs = service._build_link_objects(page_id, links)
        assert len(objs) == 1
