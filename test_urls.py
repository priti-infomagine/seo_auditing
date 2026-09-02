import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.database import async_session_factory
from app.modules.audit.models.parsed_page_facts import ParsedPageFact


PROJECT_ID = UUID("c65e0884-9d9e-42e5-9e47-84be8f1dfde7")


async def main():
    async with async_session_factory() as db:
        result = await db.execute(
            select(ParsedPageFact.url)
            .where(ParsedPageFact.project_id == PROJECT_ID)
            .limit(10)
        )

        urls = result.scalars().all()

        print("\nSTORED URLS:")
        for url in urls:
            print(url)


if __name__ == "__main__":
    asyncio.run(main())