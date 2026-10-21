"""Repositories for the SERP rank check module.

All persistence goes through Postgres — there is no Redis
cache or lock. The partial unique index
``uq_rank_checks_inflight`` provides in-flight duplicate
protection.

The ``serp_locations`` and ``serp_languages`` tables are retained
but are no longer queried at runtime — location and language are
stored as names (strings) that the DataForSEO API accepts directly.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger

from .model import RankCheck, RankCheckStatus

IN_FLIGHT_STATUSES = (RankCheckStatus.QUEUED.value, RankCheckStatus.RUNNING.value)


class RankCheckRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_in_flight(self, check: RankCheck) -> tuple[RankCheck, bool]:
        """Insert a queued check.

        Returns ``(check, created)``. When the partial unique
        index rejects the insert, the existing in-flight row is
        returned with ``created=False``.
        """
        try:
            self.db.add(check)
            await self.db.commit()
            await self.db.refresh(check)
            return check, True
        except IntegrityError:
            await self.db.rollback()
            result = await self.db.execute(
                select(RankCheck).where(
                    RankCheck.user_id.is_not_distinct_from(
                        check.user_id
                    ),
                    RankCheck.fingerprint == check.fingerprint,
                    RankCheck.status.in_(IN_FLIGHT_STATUSES),
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            logger.info(
                "serp_rank_check: duplicate in-flight request "
                "user_id=%s fingerprint=%s -> existing id=%s",
                check.user_id,
                check.fingerprint,
                existing.id,
            )
            return existing, False

    async def get(self, check_id: UUID) -> RankCheck | None:
        result = await self.db.execute(
            select(RankCheck).where(RankCheck.id == check_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self, limit: int, offset: int
    ) -> tuple[list[RankCheck], int]:
        """List all rank checks (public endpoint — no user scoping)."""
        count_stmt = select(func.count()).select_from(RankCheck)
        total = int((await self.db.execute(count_stmt)).scalar_one())
        stmt = (
            select(RankCheck)
            .order_by(RankCheck.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def mark_failed_if_pending(
        self, check_id: UUID, error_code: str
    ) -> bool:
        """Mark a queued/running check failed. Idempotent."""
        result = await self.db.execute(
            update(RankCheck)
            .where(
                RankCheck.id == check_id,
                RankCheck.status.in_(IN_FLIGHT_STATUSES),
            )
            .values(
                status=RankCheckStatus.FAILED.value,
                error_code=error_code,
                updated_at=func.now(),
            )
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def find_stuck_running(self, cutoff: datetime) -> list[RankCheck]:
        """Running checks whose ``updated_at`` is older than cutoff."""
        stmt = select(RankCheck).where(
            RankCheck.status == RankCheckStatus.RUNNING.value,
            RankCheck.updated_at < cutoff,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
