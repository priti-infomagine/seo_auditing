"""Test persist_page upsert behavior — no duplicates, updates mutable fields, returns id."""
import pytest
from sqlalchemy import func, select
from uuid import uuid4

from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.crawl_persistence_service import CrawlPersistenceService
from app.modules.crawler.models.crawl_jobs import CrawlJob


@pytest.fixture
async def persistence(db_session):
    job_id = uuid4()
    # CrawlJob requires: user_id, url, domain (all nullable=False)
    job = CrawlJob(
        id=job_id,
        user_id=uuid4(),
        url="https://example.com",
        domain="example.com",
        status="running",
    )
    repo = CrawlJobRepository(db_session)
    await repo.create(job)
    return CrawlPersistenceService(db=db_session, crawl_job_id=job_id)


@pytest.fixture
def make_page():
    def _make(**overrides):
        return CrawlPage(
            crawl_id=overrides.get("crawl_id"),
            url=overrides.get("url", "https://example.com/page"),
            normalized_url=overrides.get("normalized_url", "https://example.com/page"),
            url_hash=overrides.get("url_hash", "abc123"),
            depth=overrides.get("depth", 0),
            status_code=overrides.get("status_code", 200),
            is_crawled=True,
            is_success=True,
        )
    return _make


@pytest.mark.asyncio
async def test_persist_page_insert_returns_id(persistence, make_page):
    """First call inserts and returns a CrawlPage with id populated."""
    page = make_page(crawl_id=persistence.crawl_job_id)
    result = await persistence.persist_page(page)
    assert result.id is not None


@pytest.mark.asyncio
async def test_persist_page_upsert_no_duplicate(persistence, make_page, db_session):
    """Second call with same crawl_id + normalized_url updates, no duplicate row.

    CRITICAL: This test verifies SQLAlchemy 2.0's identity-map reconciliation
    with .returning(). When the same (crawl_id, normalized_url) row is upserted
    twice within the same DB session, the ORM should hand back the same Python
    object (same identity in the session's identity map), not a shadow copy.
    This is essential for the retry/redirect scenario in the crawl pipeline.
    """
    page1 = make_page(crawl_id=persistence.crawl_job_id, normalized_url="https://example.com/page")
    result1 = await persistence.persist_page(page1)
    first_id = result1.id
    assert first_id is not None

    page2 = make_page(
        crawl_id=persistence.crawl_job_id,
        normalized_url="https://example.com/page",  # SAME normalized_url
        url="https://example.com/page?v=2",
        status_code=201,
        depth=1,
    )
    result2 = await persistence.persist_page(page2)

    # Same id — no new row inserted
    assert result2.id == first_id

    # Identity-map reconciliation: same Python object returned for the same row
    assert result2 is result1

    # Verify only one row exists in the database
    count_result = await db_session.execute(
        select(func.count()).select_from(CrawlPage).where(
            CrawlPage.crawl_id == persistence.crawl_job_id
        )
    )
    assert count_result.scalar_one() == 1

    # Mutable fields reflect the second call
    assert result2.status_code == 201
    assert result2.depth == 1
    assert result2.url == "https://example.com/page?v=2"


@pytest.mark.asyncio
async def test_persist_page_upsert_different_url_makes_new_row(persistence, make_page):
    """Different normalized_url under same crawl_id creates a second row."""
    page1 = make_page(crawl_id=persistence.crawl_job_id, normalized_url="https://example.com/a")
    result1 = await persistence.persist_page(page1)

    page2 = make_page(crawl_id=persistence.crawl_job_id, normalized_url="https://example.com/b")
    result2 = await persistence.persist_page(page2)

    # result1.id is populated from RETURNING — compare against that, NOT page1.id
    # (page1 is the input object, never mutated by persist_page)
    assert result2.id != result1.id
