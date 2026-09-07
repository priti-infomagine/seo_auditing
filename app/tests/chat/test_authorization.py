import pytest
from uuid import uuid4
from app.modules.chat.services.authorization_service import AuthorizationService
from app.modules.crawler.models.crawl_jobs import CrawlJob


class TestAuthorizationService:
    async def test_validate_project_access_not_found(self, db_session):
        service = AuthorizationService(db_session)
        with pytest.raises(ValueError, match="Project not found"):
            await service.validate_project_access(uuid4(), uuid4())

    async def test_validate_project_access_unauthorized(self, db_session):
        service = AuthorizationService(db_session)
        project = CrawlJob(
            id=uuid4(),
            user_id=uuid4(),
            project_id=uuid4(),
            url="https://example.com",
            domain="example.com",
            status="completed",
            max_pages=100,
            max_depth=3,
        )
        db_session.add(project)
        await db_session.flush()
        with pytest.raises(PermissionError, match="Not authorized"):
            await service.validate_project_access(project.project_id, uuid4())
