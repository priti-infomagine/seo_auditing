"""
Database models package for the Core SEO crawler pipeline.

Contains the single AuditCheck SQLAlchemy model used for persisted
audit results via the write-behind policy.
"""
from __future__ import annotations

from .audit_db import AuditCheck, AuditStatus

__all__ = ["AuditCheck", "AuditStatus"]
