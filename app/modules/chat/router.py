from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.modules.chat.schemas.request import ChatRequest
from app.modules.chat.schemas.response import ChatResponse
from app.modules.chat.services.chat_service import ChatService

router = APIRouter()


@router.post("/projects/{project_id}", response_model=ChatResponse)
async def chat(
    project_id: UUID,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    service = ChatService(db=db)
    return await service.chat(project_id=project_id, message=payload.message)
