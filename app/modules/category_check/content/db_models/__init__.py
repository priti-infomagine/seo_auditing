"""
Database models package for the Content crawler pipeline.

Contains the single ContentAuditCheck SQLAlchemy model for persisted
content audit results, mirroring core_seo's AuditCheck but in a
separate table (content_audit_checks).
"""
from __future__ import annotations

from .audit_db import ContentAuditCheck, ContentAuditStatus

__all__ = ["ContentAuditCheck", "ContentAuditStatus"]
