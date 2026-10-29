"""
Base rule for content checks.

Re-exports BaseRule from core_seo.rules.base — content rules use the same
abstract base class as core SEO rules for a shared interface.
"""
from app.modules.category_check.core_seo.rules.base import BaseRule

__all__ = ["BaseRule"]
