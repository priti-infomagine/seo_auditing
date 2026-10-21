"""
Storage layer for the Core SEO module.

Provides write-behind policy implementation and DB persistence utilities.
"""
from __future__ import annotations

from .write_behind import (
    REDIS_AUDIT_TTL_SECONDS,
    WriteBehindStore,
    get_write_behind_store,
)

__all__ = ["REDIS_AUDIT_TTL_SECONDS", "WriteBehindStore", "get_write_behind_store"]
