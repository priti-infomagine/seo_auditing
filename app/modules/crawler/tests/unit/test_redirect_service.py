"""
Tests for RedirectService process_and_save_redirects.
"""
import pytest
from uuid import uuid4

from app.modules.crawler.services.redirect_service import RedirectService


class FakeDB:
    pass


class TestRedirectService:
    @pytest.mark.asyncio
    async def test_empty_redirect_list_noop(self):
        service = RedirectService(db=FakeDB(), page_id=uuid4())
        await service.process_and_save_redirects([])

    @pytest.mark.asyncio
    async def test_non_dict_items_skipped(self):
        service = RedirectService(db=FakeDB(), page_id=uuid4())
        await service.process_and_save_redirects(["not-a-dict", None])
