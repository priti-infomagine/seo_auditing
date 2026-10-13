"""Business logic for SERP rank checks.

The API never calls the provider directly: every provider call
happens inside the ``run_serp_check`` Celery task. The rank
result and the preview are separate stages — a preview failure
never fails the rank check.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logger import logger
from app.modules.seprate_checks.backlink_analysis.data_for_seo_client import (
    DataForSEOClient,
)
from app.shared.tasks.celery_app import celery_app

from .exceptions import (
    SerpParseError,
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from .model import RankCheck, RankCheckStatus, PreviewStatus
from .parser import parse_serp_response
from .preview import render_preview_html, save_preview_artifacts
from .repository import (
    RankCheckRepository,
    SerpLanguageRepository,
    SerpLocationRepository,
)
from .validation import (
    compute_fingerprint,
    normalize_domain,
    normalize_keyword,
    validate_depth,
    validate_device,
)

# ── DataForSEO client singleton ────────────────────────────────
_serp_client: DataForSEOClient | None = None
_serp_credentials: tuple[str, str] | None = None


class DataForSEOConfigurationError(RuntimeError):
    """DataForSEO credentials are missing."""


async def close_serp_client() -> None:
    global _serp_client, _serp_credentials
    if _serp_client is not None:
        await _serp_client.aclose()
    _serp_client = None
    _serp_credentials = None


async def _get_serp_client() -> DataForSEOClient:
    global _serp_client, _serp_credentials
    if not settings.DATAFORSEO_LOGIN or not settings.DATAFORSEO_PASSWORD:
        raise DataForSEOConfigurationError(
            "DataForSEO credentials are not configured"
        )
    credentials = (settings.DATAFORSEO_LOGIN, settings.DATAFORSEO_PASSWORD)
    if _serp_credentials != credentials:
        await close_serp_client()
        # max_attempts=1: retries are handled by the Celery task's
        # autoretry (max 3), not by the HTTP client.
        _serp_client = DataForSEOClient(
            settings.DATAFORSEO_LOGIN,
            settings.DATAFORSEO_PASSWORD,
            timeout=settings.SERP_PROVIDER_TIMEOUT,
            max_attempts=1,
        )
        _serp_credentials = credentials
    return _serp_client


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
        # Defensive: a raw httpx error that escaped
        # _call_provider still classifies correctly.
        if isinstance(current, httpx.TimeoutException):
            return "PROVIDER_TIMEOUT"
        if isinstance(current, httpx.HTTPStatusError):
            status_code = current.response.status_code
            if 500 <= status_code < 600:
                return "PROVIDER_5XX"
            return "PROVIDER_4XX"
        if isinstance(current, httpx.TransportError):
            return "PROVIDER_TIMEOUT"
        current = current.__cause__ or current.__context__
    return "PROVIDER_5XX"


def _raise_for_status_code(code: Any, message: Any) -> None:
    if isinstance(code, int) and code >= 50000:
        raise SerpProvider5xx(f"DataForSEO error {code}: {message}")
    if isinstance(code, int) and code >= 40000:
        raise SerpProvider4xx(f"DataForSEO error {code}: {message}")
    raise SerpProvider5xx(f"DataForSEO error {code}: {message}")


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


# ── Reference data extraction ──────────────────────────────────
def _extract_locations(body: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = body.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return []
    task = tasks[0]
    if not isinstance(task, dict):
        return []
    result = task.get("result")
    if not isinstance(result, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        code = item.get("location_code")
        name = item.get("location_name")
        if not isinstance(code, int) or not name:
            continue
        rows.append(
            {
                "location_code": code,
                "name": name,
                "country_iso": item.get("country_iso_code"),
                "location_type": item.get("location_type"),
            }
        )
    return rows


def _extract_languages(body: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = body.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return []
    task = tasks[0]
    if not isinstance(task, dict):
        return []
    result = task.get("result")
    if not isinstance(result, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        code = item.get("language_code")
        name = item.get("language_name")
        if not code or not name:
            continue
        rows.append({"language_code": code, "name": name})
    return rows


class SerpRankCheckService:
    """SERP rank check service.

    ``db`` is provided by the API layer (request-scoped session).
    Task-layer methods open their own session from
    ``async_session_factory``.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ── API-facing ───────────────────────────────────────────
    async def prepare_check(
        self,
        *,
        user_id: UUID | None = None,
        keyword: str,
        domain: str,
        location_code: int,
        language_code: str,
        device: str,
        depth: int,
        include_preview: bool,
    ) -> tuple[RankCheck, bool]:
        """Validate, fingerprint and insert a queued check.

        Returns ``(check, created)``. ``created=False`` means an
        identical in-flight check already exists.
        """
        if self.db is None:
            raise RuntimeError("prepare_check requires a database session")

        location = await SerpLocationRepository(self.db).get(location_code)
        if location is None:
            raise ValueError(f"unknown location_code: {location_code}")
        language = await SerpLanguageRepository(self.db).get(language_code)
        if language is None:
            raise ValueError(f"unknown language_code: {language_code}")

        normalized_keyword = normalize_keyword(keyword)
        normalized_domain = normalize_domain(domain)
        device = validate_device(device)
        depth = validate_depth(depth)
        fingerprint = compute_fingerprint(
            keyword=normalized_keyword,
            domain=normalized_domain,
            location_code=location_code,
            language_code=language_code,
            device=device,
            depth=depth,
            include_preview=include_preview,
        )
        check = RankCheck(
            user_id=user_id,
            keyword=normalized_keyword,
            domain=normalized_domain,
            location_code=location_code,
            language_code=language_code,
            device=device,
            depth=depth,
            include_preview=include_preview,
            fingerprint=fingerprint,
            status=RankCheckStatus.QUEUED.value,
        )
        return await RankCheckRepository(self.db).create_in_flight(check)

    # ── Task-facing: rank check ──────────────────────────────
    async def run_check_async(self, check_id: UUID) -> dict[str, Any]:
        async with async_session_factory() as session:
            repo = RankCheckRepository(session)
            check = await repo.get(check_id)
            if check is None:
                logger.warning(
                    "run_serp_check: check %s not found", check_id
                )
                return {"id": str(check_id), "status": "missing"}

            # Idempotency gate. Completed checks are a no-op (makes
            # redelivery safe). A ranked check that never enqueued
            # its preview is self-healed here.
            if check.status in (
                RankCheckStatus.RANKED.value,
                RankCheckStatus.DONE.value,
                RankCheckStatus.FAILED.value,
            ):
                if (
                    check.status == RankCheckStatus.RANKED.value
                    and check.include_preview
                    and check.preview_status == PreviewStatus.NONE.value
                ):
                    await self._enqueue_preview(check.id)
                return {"id": str(check.id), "status": check.status}

            # Crashed after the provider call — resume parsing from
            # the stored raw response without calling the provider.
            if (
                check.status == RankCheckStatus.RUNNING.value
                and check.raw_response is not None
            ):
                return await self._finalize_from_raw(check, session, repo)

            # Full path (queued, or running without a raw response:
            # a Celery retry or a crash redelivery before the
            # provider responded).
            check.status = RankCheckStatus.RUNNING.value
            await session.commit()

            try:
                body = await self._call_provider(check)
                _validate_body_status(body)
            except (SerpProviderTimeout, SerpProvider5xx):
                # Retryable: leave the check running so
                # Celery redelivers it. The task marks it
                # failed only on the final attempt.
                raise
            except Exception as exc:
                # Non-retryable (4xx, parse, unexpected):
                # fail immediately.
                check.status = RankCheckStatus.FAILED.value
                check.error_code = classify_error(exc)
                await session.commit()
                raise

            check.raw_response = body
            check.provider_cost = Decimal(str(body.get("cost") or 0))
            check.provider_called_at = datetime.now(timezone.utc)
            await session.commit()

            return await self._finalize_from_raw(check, session, repo)

    async def _call_provider(self, check: RankCheck) -> dict[str, Any]:
        client = await _get_serp_client()
        try:
            return await client.serp_google_organic_live(
                keyword=check.keyword,
                location_code=check.location_code,
                language_code=check.language_code,
                device=check.device,
                depth=check.depth,
            )
        except httpx.TimeoutException as exc:
            raise SerpProviderTimeout(str(exc)) from exc
        except httpx.TransportError as exc:
            raise SerpProviderTimeout(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if 500 <= status_code < 600:
                raise SerpProvider5xx(
                    f"provider HTTP {status_code}"
                ) from exc
            raise SerpProvider4xx(
                f"provider HTTP {status_code}"
            ) from exc

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
        check.status = RankCheckStatus.RANKED.value
        if check.include_preview:
            check.preview_status = PreviewStatus.PENDING.value
            await session.commit()
            await self._enqueue_preview(check.id)
        else:
            check.status = RankCheckStatus.DONE.value
            await session.commit()
        return {"id": str(check.id), "status": check.status}

    async def _enqueue_preview(self, check_id: UUID) -> None:
        try:
            await asyncio.to_thread(
                celery_app.send_task,
                "serp_rank_check.build_preview",
                args=[str(check_id)],
                queue="serp_preview",
            )
        except Exception as exc:
            logger.error(
                "serp_rank_check: failed to enqueue preview id=%s: %s",
                check_id,
                exc,
            )

    # ── Task-facing: preview ─────────────────────────────────
    async def build_preview_async(self, check_id: UUID) -> dict[str, Any]:
        async with async_session_factory() as session:
            repo = RankCheckRepository(session)
            check = await repo.get(check_id)
            if check is None:
                logger.warning(
                    "build_preview: check %s not found", check_id
                )
                return {"id": str(check_id), "preview_status": "missing"}
            if check.preview_status != PreviewStatus.PENDING.value:
                return {
                    "id": str(check.id),
                    "preview_status": check.preview_status,
                }
            if (
                check.status != RankCheckStatus.RANKED.value
                or not check.result
            ):
                check.preview_status = PreviewStatus.FAILED.value
                check.status = RankCheckStatus.DONE.value
                await session.commit()
                return {
                    "id": str(check.id),
                    "status": check.status,
                    "preview_status": check.preview_status,
                }
            try:
                html_content = render_preview_html(
                    keyword=check.keyword,
                    target_domain=check.domain,
                    device=check.device,
                    result=check.result,
                )
                urls = await save_preview_artifacts(
                    check.id, html_content, check.device
                )
                check.preview_html_url = urls["html_url"]
                check.preview_image_url = urls["image_url"]
                check.preview_status = PreviewStatus.DONE.value
                check.status = RankCheckStatus.DONE.value
            except Exception as exc:
                logger.error(
                    "build_preview: preview failed id=%s: %s",
                    check_id,
                    exc,
                    exc_info=True,
                )
                check.preview_status = PreviewStatus.FAILED.value
                check.status = RankCheckStatus.DONE.value
            await session.commit()
            return {
                "id": str(check.id),
                "status": check.status,
                "preview_status": check.preview_status,
            }

    # ── Task-facing: maintenance ─────────────────────────────
    async def sweep_stuck_async(self) -> dict[str, Any]:
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
                except Exception as exc:
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

    async def refresh_reference_data_async(self) -> dict[str, Any]:
        client = await _get_serp_client()
        locations_body = await client.serp_google_locations()
        languages_body = await client.serp_google_languages()
        async with async_session_factory() as session:
            locations = await SerpLocationRepository(
                session
            ).upsert_all(_extract_locations(locations_body))
            languages = await SerpLanguageRepository(
                session
            ).upsert_all(_extract_languages(languages_body))
        return {"locations": locations, "languages": languages}

    async def mark_failed_if_pending_async(
        self, check_id: UUID, error_code: str
    ) -> bool:
        async with async_session_factory() as session:
            return await RankCheckRepository(session).mark_failed_if_pending(
                check_id, error_code
            )
