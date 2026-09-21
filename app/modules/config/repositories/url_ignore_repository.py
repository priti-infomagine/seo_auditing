"""
UrlIgnorePattern repository — async DB operations for patterns and skip records.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.config.models.url_ignore_pattern import UrlIgnorePattern


class UrlIgnorePatternRepository:
    """Async repository for UrlIgnorePattern database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===== Pattern Definition Queries (record_type='pattern') =====

    async def get_active_patterns_by_scope(self, scope: str) -> List[UrlIgnorePattern]:
        """Get all active patterns for a scope, ordered by sort_order."""
        result = await self.db.execute(
            select(UrlIgnorePattern).where(
                UrlIgnorePattern.record_type == "pattern",
                UrlIgnorePattern.scope == scope,
                UrlIgnorePattern.is_active == True,
            ).order_by(UrlIgnorePattern.sort_order, UrlIgnorePattern.id)
        )
        return list(result.scalars().all())

    async def get_all_active_patterns(self) -> List[UrlIgnorePattern]:
        """Get all active patterns across all scopes, ordered by scope then sort_order."""
        result = await self.db.execute(
            select(UrlIgnorePattern).where(
                UrlIgnorePattern.record_type == "pattern",
                UrlIgnorePattern.is_active == True,
            ).order_by(UrlIgnorePattern.scope, UrlIgnorePattern.sort_order, UrlIgnorePattern.id)
        )
        return list(result.scalars().all())

    async def get_by_scope(self, scope: str) -> List[UrlIgnorePattern]:
        """Get all patterns (active + inactive) for a scope, ordered by sort_order."""
        result = await self.db.execute(
            select(UrlIgnorePattern).where(
                UrlIgnorePattern.record_type == "pattern",
                UrlIgnorePattern.scope == scope,
            ).order_by(UrlIgnorePattern.sort_order, UrlIgnorePattern.id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, pattern_id: UUID) -> Optional[UrlIgnorePattern]:
        """Get pattern by ID."""
        result = await self.db.execute(
            select(UrlIgnorePattern).where(UrlIgnorePattern.id == pattern_id)
        )
        return result.scalar_one_or_none()

    async def get_by_scope_match_pattern(self, scope: str, match_type: str, pattern: str) -> Optional[UrlIgnorePattern]:
        """Get pattern by unique scope+match_type+pattern combination."""
        result = await self.db.execute(
            select(UrlIgnorePattern).where(
                UrlIgnorePattern.record_type == "pattern",
                UrlIgnorePattern.scope == scope,
                UrlIgnorePattern.match_type == match_type,
                UrlIgnorePattern.pattern == pattern,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: Dict[str, Any]) -> UrlIgnorePattern:
        """Create a new pattern from a dict (API-friendly shorthand)."""
        obj = UrlIgnorePattern(**data)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def create_pattern(
        self,
        scope: str,
        match_type: str,
        pattern: str,
        reason: str,
        description: Optional[str] = None,
        sort_order: int = 0,
        is_default: bool = True,
    ) -> UrlIgnorePattern:
        """Create a new pattern definition."""
        obj = UrlIgnorePattern(
            record_type="pattern",
            scope=scope,
            match_type=match_type,
            pattern=pattern,
            reason=reason,
            description=description,
            sort_order=sort_order,
            is_default=is_default,
            is_active=True,
        )
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, pattern: UrlIgnorePattern, data: Dict[str, Any]) -> UrlIgnorePattern:
        """Update a pattern with dict data (API-friendly shorthand)."""
        for key, value in data.items():
            setattr(pattern, key, value)
        await self.db.flush()
        await self.db.refresh(pattern)
        return pattern

    async def update_pattern(self, pattern: UrlIgnorePattern) -> UrlIgnorePattern:
        """Update a pattern definition."""
        await self.db.flush()
        await self.db.refresh(pattern)
        return pattern

    async def deactivate_pattern(self, pattern_id: UUID) -> bool:
        """Soft delete a pattern by setting is_active=False."""
        pattern = await self.get_by_id(pattern_id)
        if pattern and pattern.record_type == "pattern":
            pattern.is_active = False
            await self.db.flush()
            return True
        return False

    async def deactivate(self, pattern_id: UUID) -> bool:
        """Alias for deactivate_pattern (API-friendly)."""
        return await self.deactivate_pattern(pattern_id)

    # ===== Skip Record Queries (record_type='skip') =====

    async def log_skip(
        self,
        audit_id: UUID,
        url: str,
        normalized_url: str,
        reason: str,
        scope: str,
        matched_pattern_id: Optional[UUID] = None,
    ) -> UrlIgnorePattern:
        """Insert a skip record."""
        obj = UrlIgnorePattern(
            record_type="skip",
            audit_id=audit_id,
            url=url,
            normalized_url=normalized_url,
            reason=reason,
            scope=scope,
            matched_pattern_id=matched_pattern_id,
        )
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def get_skips_by_audit(self, audit_id: UUID, skip: int = 0, limit: int = 100) -> tuple:
        """Get skip records for an audit with pagination. Returns (records, total_count)."""
        count_result = await self.db.execute(
            select(func.count(UrlIgnorePattern.id)).where(
                UrlIgnorePattern.record_type == "skip",
                UrlIgnorePattern.audit_id == audit_id,
            )
        )
        total = count_result.scalar() or 0

        result = await self.db.execute(
            select(UrlIgnorePattern).where(
                UrlIgnorePattern.record_type == "skip",
                UrlIgnorePattern.audit_id == audit_id,
            ).order_by(UrlIgnorePattern.recorded_at).offset(skip).limit(limit)
        )
        records = list(result.scalars().all())
        return records, total

    async def get_skip_breakdown_by_audit(self, audit_id: UUID) -> Dict[str, int]:
        """Get skip reason counts for an audit."""
        result = await self.db.execute(
            select(UrlIgnorePattern.reason, func.count(UrlIgnorePattern.id))
            .where(
                UrlIgnorePattern.record_type == "skip",
                UrlIgnorePattern.audit_id == audit_id,
            )
            .group_by(UrlIgnorePattern.reason)
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_skip_count_by_audit(self, audit_id: UUID) -> int:
        """Get total skip count for an audit."""
        result = await self.db.execute(
            select(func.count(UrlIgnorePattern.id)).where(
                UrlIgnorePattern.record_type == "skip",
                UrlIgnorePattern.audit_id == audit_id,
            )
        )
        return result.scalar() or 0

    async def get_skips_by_check_id(self, check_id: UUID) -> List[UrlIgnorePattern]:
        """Get all skip records for a Lighthouse check (uses same crawl_jobs table)."""
        records, _ = await self.get_skips_by_audit(check_id)
        return records

    async def get_skip_breakdown_by_check_id(self, check_id: UUID) -> Dict[str, int]:
        """Get skip reason counts for a Lighthouse check."""
        return await self.get_skip_breakdown_by_audit(check_id)