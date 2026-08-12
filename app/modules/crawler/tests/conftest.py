"""
Shared configuration, fixtures, and helpers for the crawler test-suite.

When tests run under pytest the session-scoped ``crawl_result`` fixture
crawls **https://www.reddit.com** once and shares the result with every test.

Every test also saves its extracted output to::

    app/modules/crawler/results/<domain>/<name>.json

Both the pytest fixtures and the helper functions can be used when running
a test file directly, e.g.::

    python app/modules/crawler/tests/document.py
"""
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path – ensure the backend root is importable so that
# ``from app.modules…`` works both under pytest and when running a test
# file directly (``python …/tests/document.py``).
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[4]   # tests/ → crawler/ → modules/ → app/ → backend/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import json                                   # noqa: E402
from dataclasses import asdict, is_dataclass   # noqa: E402
from typing import Any                         # noqa: E402

import pytest                                  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEST_URL = "https://www.reddit.com"
DOMAIN = "www.reddit.com"

# Results directory:  crawler/results/<domain>/
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results" / DOMAIN
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def save_result(filename: str, data: Any) -> str:
    """Persist *data* as JSON inside ``crawler/results/<domain>/``.

    *data* may be a plain dict or a dataclass instance.  Non-serialisable
    fields (e.g. the BeautifulSoup ``soup`` attribute on DocumentFacts)
    are stripped automatically so the file is always valid JSON.

    Returns the absolute path of the written file.
    """

    def _serialize(obj: Any) -> Any:
        """Walk dataclasses / dicts / lists, skipping non-serialisable fields."""
        if is_dataclass(obj) and not isinstance(obj, type):
            result: dict = {}
            for f in __import__("dataclasses").fields(obj):
                if f.name == "soup":            # BeautifulSoup – cannot serialise
                    continue
                result[f.name] = _serialize(getattr(obj, f.name))
            return result
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_serialize(i) for i in obj]
        return obj

    filepath = RESULTS_DIR / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    serialisable = _serialize(data)

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(serialisable, fh, indent=2, ensure_ascii=False, default=str)
    return str(filepath)


async def get_crawl_result():
    """Crawl *TEST_URL* with :class:`PageCrawlService` and return the result.

    Raises ``AssertionError`` if the crawl fails so that test output is clear.
    """
    from app.modules.crawler.services.page_crawl_service import PageCrawlService

    service = PageCrawlService()
    result = await service.crawl_page(TEST_URL)
    assert result.error is None, f"Crawl failed: {result.error}"
    assert result.document is not None, "No document returned from crawl"
    assert result.fetch_result is not None, "No fetch result returned from crawl"
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
async def crawl_result():
    """Session-scoped crawl of https://www.reddit.com (shared by all tests)."""
    return await get_crawl_result()


@pytest.fixture
def results_dir() -> Path:
    """Return the results directory for the test domain."""
    return RESULTS_DIR
