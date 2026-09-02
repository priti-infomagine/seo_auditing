import asyncio
from uuid import UUID

from app.core.database import async_session_factory
from app.modules.chat.tools import build_chat_tools


PROJECT_ID = UUID("c65e0884-9d9e-42e5-9e47-84be8f1dfde7")


async def main():
    async with async_session_factory() as db:
        tools = build_chat_tools(db, PROJECT_ID)

        print("\nTOOLS:")
        for tool in tools:
            print(f"- {tool.name}: {tool.description[:200]}")

        print(f"\nTOTAL TOOLS: {len(tools)}")


if __name__ == "__main__":
    asyncio.run(main())