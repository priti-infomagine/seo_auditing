"""Rules package for the Content crawler pipeline.

Re-exports BaseRule from core_seo for structural consistency.
"""
from __future__ import annotations

from app.modules.category_check.core_seo.rules.base import BaseRule
from .registry import ContentRuleRegistry, default_content_registry

__all__ = ["BaseRule", "ContentRuleRegistry", "default_content_registry"]
