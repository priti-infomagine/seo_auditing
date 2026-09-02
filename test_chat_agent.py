import asyncio

from langchain.agents import create_agent
from langchain_ollama import ChatOllama


async def main():
    model = ChatOllama(
        base_url="http://127.0.0.1:11434",
        model="qwen3:1.7b",
        temperature=0.1,
        timeout=60,
    )

    agent = create_agent(
        model=model,
        tools=[],
        system_prompt="You are a helpful assistant.",
    )

    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly: AGENT_OK",
                }
            ]
        },
        config={"recursion_limit": 6},
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())