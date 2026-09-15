#!/usr/bin/env python
"""Interactive CLI tester for the chat API.


"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.modules.chat.services.chat_service import ChatService


def _resolve_audit_id() -> UUID:
    if len(sys.argv) > 1:
        return UUID(sys.argv[1].strip())
    raw = input("Enter audit_id: ").strip()
    return UUID(raw)


async def main() -> None:
    audit_id = _resolve_audit_id()
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        service = ChatService(db=db)

        print(f"Chat Tester - Project: {audit_id}")
        print("Type your question and press Enter. Type 'exit' or press Ctrl+C to quit.\n")

        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not question or question.lower() in {"exit", "quit"}:
                break

            try:
                response = await service.chat(
                    audit_id=audit_id,
                    message=question,
                )
                print(f"\nBot: {response.answer}\n")
            except Exception as exc:  # noqa: BLE001
                print(f"\nError: {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
