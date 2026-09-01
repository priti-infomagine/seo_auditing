from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.parsed_page_facts import ParsedPageFact
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.repositories.page_seo_data_repository import PageSEODataRepository


class PageRetriever:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.parsed_repo = ParsedPageFactRepository(db)
        self.seo_repo = PageSEODataRepository(db)

    async def get_page_facts(self, project_id: UUID, page_url: str) -> Optional[dict]:
        facts = await self.parsed_repo.get_by_project_id(project_id)
        matched = None
        for fact in facts:
            if fact.url == page_url:
                matched = fact
                break
        if matched is None:
            return None
        seo = None
        if matched.page_id:
            seo = await self.seo_repo.get_by_page_id(matched.page_id)
        parsed_data = matched.parsed_data or {}
        return {
            "page_id": str(matched.page_id) if matched.page_id else None,
            "url": matched.url,
            "domain": matched.domain,
            "title": (matched.page_facts or {}).get("title", ""),
            "meta_description": (matched.page_facts or {}).get("meta_description", ""),
            "canonical": (matched.page_facts or {}).get("canonical", ""),
            "headings": parsed_data.get("headings", []),
            "content": {
                "word_count": (matched.page_facts or {}).get("word_count", 0),
                "text": ((matched.page_facts or {}).get("content_text") or "")[:2000],
            },
            "technical": parsed_data.get("technical", {}),
            "seo": seo.model_dump(mode="json") if seo else {},
        }
