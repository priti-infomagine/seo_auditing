import json
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage, ToolMessage

from app.modules.chat.services.chat_service import ChatService
from app.modules.chat.schemas.response import ChatResponse


class TestChatService:
    @pytest.fixture
    def service(self, db_session):
        return ChatService(db=db_session)

    async def test_chat_no_completed_audit(self, service):
        project_id = uuid4()
        response = await service.chat(project_id, "How is my website doing?")
        assert isinstance(response, ChatResponse)
        assert response.audit_id is None
        assert "No completed audit" in response.answer

    async def test_chat_agent_invoked_with_recursion_limit(self, service):
        project_id = uuid4()
        mock_audit = {
            "id": uuid4(),
            "project_id": str(project_id),
            "overall_score": 50.0,
            "grade": "needs_improvement",
            "total_pages_scored": 10,
            "total_rules_evaluated": 50,
            "critical_issues": 2,
            "warnings": 5,
            "category_scores": {},
            "top_issues": {},
        }

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                AIMessage(content="Because of X, Y, Z."),
            ]
        }

        with patch.object(service.audit_retriever, "get_latest_completed", new_callable=AsyncMock, return_value=mock_audit):
            with patch("app.modules.chat.services.chat_service.create_agent", return_value=mock_agent):
                response = await service.chat(project_id, "Why is my score low?")
                assert isinstance(response, ChatResponse)
                mock_agent.ainvoke.assert_called_once()
                call_kwargs = mock_agent.ainvoke.call_args
                assert call_kwargs.kwargs.get("config") == {"recursion_limit": 6}

    async def test_chat_strips_think_tags(self, service):
        project_id = uuid4()
        mock_audit = {
            "id": uuid4(),
            "project_id": str(project_id),
            "overall_score": 50.0,
            "grade": "needs_improvement",
            "total_pages_scored": 10,
            "total_rules_evaluated": 50,
            "critical_issues": 2,
            "warnings": 5,
            "category_scores": {},
            "top_issues": {},
        }

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                AIMessage(content="<think>internal reasoning</think>\nActual answer."),
            ]
        }

        with patch.object(service.audit_retriever, "get_latest_completed", new_callable=AsyncMock, return_value=mock_audit):
            with patch("app.modules.chat.services.chat_service.create_agent", return_value=mock_agent):
                response = await service.chat(project_id, "test")
                assert "<think>" not in response.answer
                assert response.answer == "Actual answer."

    async def test_chat_references_from_tool_messages(self, service):
        project_id = uuid4()
        mock_audit = {
            "id": uuid4(),
            "project_id": str(project_id),
            "overall_score": 50.0,
            "grade": "needs_improvement",
            "total_pages_scored": 10,
            "total_rules_evaluated": 50,
            "critical_issues": 2,
            "warnings": 5,
            "category_scores": {},
            "top_issues": {},
        }

        tool_output = json.dumps([
            {"rule_id": "on_page_001", "severity": "warning", "message": "Title too long"},
            {"page_url": "https://example.com/about", "rule_id": "on_page_001"},
        ])

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "messages": [
                AIMessage(content="Answer."),
                ToolMessage(content=tool_output, tool_call_id="abc"),
            ]
        }

        with patch.object(service.audit_retriever, "get_latest_completed", new_callable=AsyncMock, return_value=mock_audit):
            with patch("app.modules.chat.services.chat_service.create_agent", return_value=mock_agent):
                response = await service.chat(project_id, "test")
                assert len(response.references) == 2
                ref_types = {r.type for r in response.references}
                assert "rule" in ref_types
                assert "page" in ref_types
