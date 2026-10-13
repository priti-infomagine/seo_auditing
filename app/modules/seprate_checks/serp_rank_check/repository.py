"""Repositories for the SERP rank check module.

All persistence goes through Postgres — there is no Redis
cache or lock. The partial unique index
``uq_rank_checks_inflight`` provides in-flight duplicate
protection.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger

from .model import RankCheck, RankCheckStatus, SerpLanguage, SerpLocation

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
                    RankCheck.user_id == check.user_id,
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

    async def get_by_user(
        self, check_id: UUID, user_id: UUID
    ) -> RankCheck | None:
        result = await self.db.execute(
            select(RankCheck).where(
                RankCheck.id == check_id,
                RankCheck.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[RankCheck], int]:
        count_stmt = (
            select(func.count())
            .select_from(RankCheck)
            .where(RankCheck.user_id == user_id)
        )
        total = int((await self.db.execute(count_stmt)).scalar_one())
        stmt = (
            select(RankCheck)
            .where(RankCheck.user_id == user_id)
            .order_by(RankCheck.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

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


class SerpLocationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, q: str | None, limit: int, offset: int
    ) -> list[SerpLocation]:
        stmt = select(SerpLocation).order_by(SerpLocation.name)
        if q:
            stmt = stmt.where(SerpLocation.name.ilike(f"%{q}%"))
        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, q: str | None) -> int:
        stmt = select(func.count()).select_from(SerpLocation)
        if q:
            stmt = stmt.where(SerpLocation.name.ilike(f"%{q}%"))
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get(self, location_code: int) -> SerpLocation | None:
        result = await self.db.execute(
            select(SerpLocation).where(
                SerpLocation.location_code == location_code
            )
        )
        return result.scalar_one_or_none()

    async def upsert_all(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        stmt = pg_insert(SerpLocation).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["location_code"],
            set_={
                "name": stmt.excluded.name,
                "country_iso": stmt.excluded.country_iso,
                "location_type": stmt.excluded.location_type,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return len(rows)


class SerpLanguageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, limit: int, offset: int
    ) -> list[SerpLanguage]:
        stmt = (
            select(SerpLanguage)
            .order_by(SerpLanguage.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(SerpLanguage)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get(self, language_code: str) -> SerpLanguage | None:
        result = await self.db.execute(
            select(SerpLanguage).where(
                SerpLanguage.language_code == language_code
            )
        )
        return result.scalar_one_or_none()

    async def upsert_all(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        stmt = pg_insert(SerpLanguage).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["language_code"],
            set_={"name": stmt.excluded.name},
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return len(rows)
