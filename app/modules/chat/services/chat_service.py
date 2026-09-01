import json
import re
from uuid import UUID

from fastapi import HTTPException

from app.core.config import settings
from app.modules.chat.knowledge.rule_guidance import RULE_GUIDANCE
from app.modules.chat.prompts.system_prompt import SYSTEM_PROMPT
from app.modules.chat.retrieval.audit_retriever import AuditRetriever
from app.modules.chat.retrieval.category_retriever import CategoryRetriever
from app.modules.chat.retrieval.issue_retriever import IssueRetriever
from app.modules.chat.retrieval.page_retriever import PageRetriever
from app.modules.chat.schemas.response import ChatResponse
from app.modules.chat.services.response_validator import ResponseValidator
from app.modules.chat.tools import build_chat_tools
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage


class ChatService:
    def __init__(self, db) -> None:
        self.db = db
        self.audit_retriever = AuditRetriever(db)
        self.issue_retriever = IssueRetriever(db)
        self.page_retriever = PageRetriever(db)
        self.category_retriever = CategoryRetriever(db)
        self.response_validator = ResponseValidator()

    async def chat(self, project_id: UUID, message: str) -> ChatResponse:
        audit = await self.audit_retriever.get_latest_completed(project_id)
        if audit is None:
            return ChatResponse(
                project_id=str(project_id),
                audit_id=None,
                answer="No completed audit is available for this project yet.",
                references=[],
            )

        tools = build_chat_tools(self.db, project_id)

        from langchain_ollama import ChatOllama
        model = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=settings.OLLAMA_TEMPERATURE,
            timeout=settings.OLLAMA_TIMEOUT,
        )

        audit_summary = (
            f"AUDIT SUMMARY\n"
            f"Overall score: {audit.get('overall_score')}/100 ({audit.get('grade')})\n"
            f"Total pages scored: {audit.get('total_pages_scored')}\n"
            f"Total rules evaluated: {audit.get('total_rules_evaluated')}\n"
            f"Critical issues: {audit.get('critical_issues')}\n"
            f"Warnings: {audit.get('warnings')}\n"
        )
        system_prompt = f"{SYSTEM_PROMPT}\n\n{audit_summary}"
        agent = create_agent(model=model, tools=tools, system_prompt=system_prompt)

        messages = [{"role": "user", "content": message}]

        try:
            # recursion_limit=6 is a starting point for qwen3:1.7b; tune empirically.
            result = await agent.ainvoke({"messages": messages}, config={"recursion_limit": 6})
        except RuntimeError:
            raise HTTPException(status_code=503, detail="Chat service temporarily unavailable")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Chat service temporarily unavailable: {exc}")

        ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
        answer = ai_messages[-1].content if ai_messages else ""
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        validated = self.response_validator.validate(answer, tool_messages)

        return ChatResponse(
            project_id=str(project_id),
            audit_id=str(audit["id"]) if audit.get("id") else None,
            answer=validated["answer"],
            references=validated["references"],
        )
