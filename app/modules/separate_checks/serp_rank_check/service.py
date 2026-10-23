"""Business logic for SERP rank checks.

The API endpoint calls DataForSEO directly (synchronous flow):
validate input → call provider → parse → persist → return result.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logger import logger

from .client import get_serp_client
from .exceptions import (
    SerpParseError,
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from .model import RankCheck, RankCheckStatus
from .parser import parse_serp_response
from .repository import RankCheckRepository
from .validation import (
    compute_fingerprint,
    normalize_domain,
    normalize_keyword,
    validate_depth,
    validate_device,
)


# ── Error classification ───────────────────────────────────────
def classify_error(exc: BaseException) -> str:
    """Map an exception to a stored error_code.

    Walks the cause/context chain so a wrapped
    ``MaxRetriesExceededError`` still resolves to the original
    provider error. Defaults to ``PROVIDER_5XX`` (the only
    retryable errors are timeouts and 5xx).
    """
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, SerpProviderTimeout):
            return "PROVIDER_TIMEOUT"
        if isinstance(current, SerpProvider4xx):
            return "PROVIDER_4XX"
        if isinstance(current, SerpProvider5xx):
            return "PROVIDER_5XX"
        if isinstance(current, SerpParseError):
            return "PARSE_ERROR"
        current = current.__cause__ or current.__context__
    return "PROVIDER_5XX"


def _validate_body_status(body: dict[str, Any]) -> None:
    """Raise a typed provider error for non-20000 status codes."""
    status_code = body.get("status_code")
    if status_code == 20000:
        tasks = body.get("tasks")
        if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
            task_code = tasks[0].get("status_code")
            if task_code != 20000:
                _raise_for_status_code(
                    task_code, tasks[0].get("status_message")
                )
        return
    _raise_for_status_code(status_code, body.get("status_message"))


def _raise_for_status_code(code: Any, message: Any) -> None:
    if isinstance(code, int) and code >= 50000:
        raise SerpProvider5xx(f"DataForSEO error {code}: {message}")
    if isinstance(code, int) and code >= 40000:
        raise SerpProvider4xx(f"DataForSEO error {code}: {message}")
    raise SerpProvider5xx(f"DataForSEO error {code}: {message}")


# ── Error-handling correction ──────────────────────────────────
# An empty *items* list in a valid 20000 response means "no results
# for this keyword" — that is a successful outcome, not an error.
# Empty / malformed *response bodies* (missing tasks, invalid JSON)
# DO raise and are caught by the service's try/except and classified
# via classify_error().


class SerpRankCheckService:
    """SERP rank check service.

    ``db`` is provided by the API layer (request-scoped session).
    Task-layer methods open their own session from
    ``async_session_factory``.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ── API-facing: synchronous check ──────────────────────
    async def check_serp_rank(
        self,
        *,
        user_id: UUID | None = None,
        keyword: str,
        domain: str,
        location_name: str,
        language_name: str,
        device: str,
        depth: int,
    ) -> tuple[RankCheck, bool]:
        """Validate, call DataForSEO, parse, persist, and return.

        This is the single entry point for the rank-check workflow.
        The endpoint calls this method synchronously — no Celery
        task is enqueued for the check itself.

        Returns ``(check, created)``.  ``created=False`` means an
        identical in-flight check already exists (deduplication via
        the partial unique index).
        """
        if self.db is None:
            raise RuntimeError("check_serp_rank requires a database session")

        normalized_keyword = normalize_keyword(keyword)
        normalized_domain = normalize_domain(domain)
        device = validate_device(device)
        depth = validate_depth(depth)
        location_name = location_name.strip()
        if not location_name:
            raise ValueError("location must not be blank")
        language_name = language_name.strip()
        if not language_name:
            raise ValueError("language must not be blank")

        fingerprint = compute_fingerprint(
            keyword=normalized_keyword,
            domain=normalized_domain,
            location_name=location_name,
            language_name=language_name,
            device=device,
            depth=depth,
        )

        check = RankCheck(
            user_id=user_id,
            keyword=normalized_keyword,
            domain=normalized_domain,
            location_name=location_name,
            language_name=language_name,
            device=device,
            depth=depth,
            fingerprint=fingerprint,
            status=RankCheckStatus.RUNNING.value,
        )

        repo = RankCheckRepository(self.db)
        check, created = await repo.create_in_flight(check)
        if not created:
            await self.db.refresh(check)
            return check, False

        try:
            client = await get_serp_client()
            body = await client.serp_google_organic_live_advanced(
                keyword=normalized_keyword,
                location_name=location_name,
                language_name=language_name,
                device=device,
                depth=depth,
            )
            _validate_body_status(body)

            check.raw_response = body
            check.provider_cost = Decimal(str(body.get("cost") or 0))
            check.provider_called_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(check)

            result = parse_serp_response(
                body,
                normalized_domain,
                depth,
                settings.SERP_TOP_RESULTS_LIMIT,
            )
            check.result = result
            check.status = RankCheckStatus.DONE.value
            await self.db.commit()
            await self.db.refresh(check)

            return check, True

        except (SerpProviderTimeout, SerpProvider5xx):
            await self.db.commit()
            raise
        except Exception as exc:
            check.status = RankCheckStatus.FAILED.value
            check.error_code = classify_error(exc)
            await self.db.commit()
            raise

    # ── Task-facing: maintenance ────────────────────────────
    async def sweep_stuck_async(self) -> dict[str, Any]:
        """Recover checks stuck in ``running`` for too long.

        Jobs with a stored raw response resume parsing; the rest are
        marked failed (STUCK).
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=settings.SERP_STUCK_JOB_TIMEOUT_SECONDS
        )
        async with async_session_factory() as session:
            repo = RankCheckRepository(session)
            stuck = await repo.find_stuck_running(cutoff)
            resumed = 0
            failed = 0
            for check in stuck:
                try:
                    if check.raw_response is not None:
                        await self._finalize_from_raw(check, session, repo)
                        resumed += 1
                    else:
                        check.status = RankCheckStatus.FAILED.value
                        check.error_code = "STUCK"
                        await session.commit()
                        failed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "sweep_stuck_checks: recovery failed id=%s: %s",
                        check.id,
                        exc,
                        exc_info=True,
                    )
                    await session.rollback()
                    failed += 1
            return {
                "swept": len(stuck),
                "resumed": resumed,
                "failed": failed,
            }

    async def _finalize_from_raw(
        self,
        check: RankCheck,
        session: AsyncSession,
        repo: RankCheckRepository,
    ) -> dict[str, Any]:
        """Parse the stored raw response and persist the result."""
        try:
            result = parse_serp_response(
                check.raw_response,
                check.domain,
                check.depth,
                settings.SERP_TOP_RESULTS_LIMIT,
            )
        except SerpParseError as exc:
            logger.error(
                "serp_rank_check: parse failed id=%s: %s", check.id, exc
            )
            check.status = RankCheckStatus.FAILED.value
            check.error_code = "PARSE_ERROR"
            await session.commit()
            return {"id": str(check.id), "status": check.status}

        check.result = result
        check.status = RankCheckStatus.DONE.value
        await session.commit()
        return {"id": str(check.id), "status": check.status}

    async def mark_failed_if_pending_async(
        self, check_id: UUID, error_code: str
    ) -> bool:
        async with async_session_factory() as session:
            return await RankCheckRepository(session).mark_failed_if_pending(
                check_id, error_code
            )
