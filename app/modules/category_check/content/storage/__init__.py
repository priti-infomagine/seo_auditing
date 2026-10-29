"""
Storage layer for the Content module.

Provides ContentWriteBehindStore — a write-behind policy implementation
that buffers content audit state in Redis (content: prefix namespace)
and flushes to the content_audit_checks table asynchronously.
"""
from __future__ import annotations

from app.modules.category_check.core_seo.storage.write_behind import REDIS_AUDIT_TTL_SECONDS, WriteBehindStore
from .content_write_behind import ContentWriteBehindStore

__all__ = ["REDIS_AUDIT_TTL_SECONDS", "WriteBehindStore", "ContentWriteBehindStore"]
