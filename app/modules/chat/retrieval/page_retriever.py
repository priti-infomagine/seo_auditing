
import re
from typing import Optional
from uuid import UUID
import time
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repositories.parsed_page_fact_repository import (
    ParsedPageFactRepository,
)
from app.modules.crawler.repositories.page_seo_data_repository import (
    PageSEODataRepository,
)


class PageRetriever:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.parsed_repo = ParsedPageFactRepository(db)
        self.seo_repo = PageSEODataRepository(db)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        Normalize URLs coming from the LLM.

        Handles:
        - Markdown links:
          [https://example.com](https://example.com)
        - Whitespace
        - Trailing slash differences
        """
        if not url:
            return ""

        url = url.strip()

        # Extract URL from Markdown link:
        # [https://example.com](https://example.com)
        markdown_match = re.fullmatch(
            r"\[([^\]]+)\]\(([^)]+)\)",
            url,
        )

        if markdown_match:
            url = markdown_match.group(2).strip()

        # Remove accidental surrounding quotes.
        url = url.strip("\"'")

        # Normalize trailing slash.
        if url.endswith("/"):
            url = url[:-1]

        return url

    async def get_page_facts(
        self,
        project_id: UUID,
        page_url: str,
    ) -> Optional[dict]:
        requested_url = self._normalize_url(page_url)
        start = time.perf_counter()

        

        facts = await self.parsed_repo.get_by_project_id(project_id)

        matched = None

        for fact in facts:
            stored_url = self._normalize_url(fact.url)

            if stored_url == requested_url:
                matched = fact
                break

        if matched is None:
            return None

        seo = None

        if matched.page_id:
            seo = await self.seo_repo.get_by_page_id(matched.page_id)

        parsed_data = matched.parsed_data or {}
        page_facts = matched.page_facts or {}

        return {
            "page_id": str(matched.page_id) if matched.page_id else None,
            "url": matched.url,
            "domain": matched.domain,

            "title": page_facts.get("title", ""),
            "meta_description": page_facts.get("meta_description", ""),
            "canonical": page_facts.get("canonical", ""),

            "headings": parsed_data.get("headings", []),

            "content": {
                "word_count": page_facts.get("word_count", 0),
                "text": (page_facts.get("content_text") or "")[:2000],
            },

            "technical": parsed_data.get("technical", {}),

            "seo": {
                "id": str(seo.id) if seo else None,
                "page_id": str(seo.page_id) if seo else None,
                "title": seo.title if seo else None,
                "title_length": seo.title_length if seo else None,
                "meta_description": seo.meta_description if seo else None,
                "meta_description_length": (
                    seo.meta_description_length if seo else None
                ),
                "canonical": seo.canonical if seo else None,
                "robots_meta": seo.robots_meta if seo else None,
                "language": seo.language if seo else None,
                "charset": seo.charset if seo else None,
                "viewport": seo.viewport if seo else None,
                "favicon": seo.favicon if seo else None,
                "word_count": seo.word_count if seo else None,
                "content_hash": seo.content_hash if seo else None,
                "page_metadata": seo.page_metadata if seo else {},
                "headings": seo.headings if seo else {},
                "content": seo.content if seo else {},
                "structured_data": seo.structured_data if seo else {},
                "social": seo.social if seo else {},
                "indexability": seo.indexability if seo else {},
                "accessibility": seo.accessibility if seo else {},
            },
        
        }


# from typing import Optional
# from uuid import UUID

# from sqlalchemy.ext.asyncio import AsyncSession

# from app.modules.audit.repositories.parsed_page_fact_repository import (
#     ParsedPageFactRepository,
# )
# from app.modules.crawler.repositories.page_seo_data_repository import (
#     PageSEODataRepository,
# )


# class PageRetriever:
#     def __init__(self, db: AsyncSession) -> None:
#         self.db = db
#         self.parsed_repo = ParsedPageFactRepository(db)
#         self.seo_repo = PageSEODataRepository(db)

#     @staticmethod
#     def _serialize_seo(seo) -> dict:
#         if seo is None:
#             return {}

#         return {
#             "id": str(seo.id),
#             "page_id": str(seo.page_id),
#             "title": seo.title,
#             "title_length": seo.title_length,
#             "meta_description": seo.meta_description,
#             "meta_description_length": seo.meta_description_length,
#             "canonical": seo.canonical,
#             "robots_meta": seo.robots_meta,
#             "language": seo.language,
#             "charset": seo.charset,
#             "viewport": seo.viewport,
#             "favicon": seo.favicon,
#             "word_count": seo.word_count,
#             "content_hash": seo.content_hash,
#             "page_metadata": seo.page_metadata or {},
#             "headings": seo.headings or {},
#             "content": seo.content or {},
#             "structured_data": seo.structured_data or {},
#             "social": seo.social or {},
#             "indexability": seo.indexability or {},
#             "accessibility": seo.accessibility or {},
#         }

#     async def get_page_facts(
#         self,
#         project_id: UUID,
#         page_url: str,
#     ) -> Optional[dict]:
#         facts = await self.parsed_repo.get_by_project_id(project_id)

#         matched = None

#         for fact in facts:
#             if fact.url == page_url:
#                 matched = fact
#                 break

#         if matched is None:
#             return None

#         seo = None

#         if matched.page_id:
#             seo = await self.seo_repo.get_by_page_id(matched.page_id)

#         parsed_data = matched.parsed_data or {}
#         page_facts = matched.page_facts or {}

#         return {
#             "page_id": str(matched.page_id) if matched.page_id else None,
#             "url": matched.url,
#             "domain": matched.domain,
#             "title": page_facts.get("title", ""),
#             "meta_description": page_facts.get("meta_description", ""),
#             "canonical": page_facts.get("canonical", ""),
#             "headings": parsed_data.get("headings", []),
#             "content": {
#                 "word_count": page_facts.get("word_count", 0),
#                 "text": (page_facts.get("content_text") or "")[:2000],
#             },
#             "technical": parsed_data.get("technical", {}),
#             "seo": self._serialize_seo(seo),
#         }




# from typing import Optional
# from uuid import UUID

# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.modules.audit.models.parsed_page_facts import ParsedPageFact
# from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
# from app.modules.crawler.models.page_seo_data import PageSEOData
# from app.modules.crawler.repositories.page_seo_data_repository import PageSEODataRepository


# class PageRetriever:
#     def __init__(self, db: AsyncSession) -> None:
#         self.db = db
#         self.parsed_repo = ParsedPageFactRepository(db)
#         self.seo_repo = PageSEODataRepository(db)

#     async def get_page_facts(self, project_id: UUID, page_url: str) -> Optional[dict]:
#         facts = await self.parsed_repo.get_by_project_id(project_id)
#         matched = None
#         for fact in facts:
#             if fact.url == page_url:
#                 matched = fact
#                 break
#         if matched is None:
#             return None
#         seo = None
#         if matched.page_id:
#             seo = await self.seo_repo.get_by_page_id(matched.page_id)
#         parsed_data = matched.parsed_data or {}
#         return {
#             "page_id": str(matched.page_id) if matched.page_id else None,
#             "url": matched.url,
#             "domain": matched.domain,
#             "title": (matched.page_facts or {}).get("title", ""),
#             "meta_description": (matched.page_facts or {}).get("meta_description", ""),
#             "canonical": (matched.page_facts or {}).get("canonical", ""),
#             "headings": parsed_data.get("headings", []),
#             "content": {
#                 "word_count": (matched.page_facts or {}).get("word_count", 0),
#                 "text": ((matched.page_facts or {}).get("content_text") or "")[:2000],
#             },
#             "technical": parsed_data.get("technical", {}),
#             "seo": seo.model_dump(mode="json") if seo else {},
#         }
