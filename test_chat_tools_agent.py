import asyncio
from uuid import UUID
from app.core.config import settings
from app.core.database import async_session_factory
from app.modules.chat.tools import build_chat_tools
from langchain.agents import create_agent
from langchain_ollama import ChatOllama


PROJECT_ID = UUID("c65e0884-9d9e-42e5-9e47-84be8f1dfde7")


async def main():
    async with async_session_factory() as db:
        tools = build_chat_tools(db, PROJECT_ID)

        model = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=0.1,
            timeout=120,
        )

        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=(
                "You are an SEO audit assistant. "
                "Use the available tools when the user asks about "
                "audit issues or page SEO data. "
                "Be concise."
            ),
        )

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Get the SEO facts for this page: "
                            "https://allworthfinancial.com/podcast/"
                            "simply-money/december-13-2024"
                        ),
                    }
                ]
            },
            config={"recursion_limit": 6},
        )

        print("\n===== AGENT RESULT =====\n")

        for message in result["messages"]:
            print(type(message).__name__)
            print(message)
            print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())