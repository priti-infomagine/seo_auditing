"""
CrawlPipelineEvent - Event bus for crawler pipeline stages.
"""
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List


class CrawlPipelineEvent(str, Enum):
    PAGE_START = "page_start"
    PAGE_FETCHED = "page_fetched"
    PAGE_EXTRACTED = "page_extracted"
    PAGE_PERSISTED = "page_persisted"
    PAGE_ERROR = "page_error"
    REDISCOVERED = "rediscovered"
    SCHEDULER_START = "scheduler_start"
    SCHEDULER_COMPLETE = "scheduler_complete"


class CrawlPipelineBus:
    """Simple event bus for crawler pipeline stages."""

    def __init__(self) -> None:
        self._subscribers: Dict[CrawlPipelineEvent, List[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}

    def subscribe(
        self,
        event: CrawlPipelineEvent,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._subscribers.setdefault(event, []).append(handler)

    async def emit(self, event: CrawlPipelineEvent, **kwargs: Any) -> None:
        for handler in self._subscribers.get(event, []):
            try:
                await handler(kwargs)
            except Exception:
                pass
