import asyncio
from uuid import UUID

from app.core.database import async_session_factory
from app.modules.chat.retrieval.page_retriever import PageRetriever


PROJECT_ID = UUID("c65e0884-9d9e-42e5-9e47-84be8f1dfde7")


async def main():
    async with async_session_factory() as db:
        retriever = PageRetriever(db)

        facts = await retriever.get_page_facts(
            project_id=PROJECT_ID,
            page_url="https://allworthfinancial.com/podcast/simply-money/december-13-2024",
        )

        print("\nRESULT:")
        print(facts)


if __name__ == "__main__":
    asyncio.run(main())