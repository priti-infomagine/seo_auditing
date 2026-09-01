import pytest
from app.modules.chat.router import router


class TestChatRouter:
    def test_chat_route_registered(self):
        routes = [route.path for route in router.routes]
        assert "/projects/{project_id}" in routes
