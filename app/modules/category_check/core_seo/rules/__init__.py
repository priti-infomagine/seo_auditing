"""Rules package for the Core SEO crawler pipeline."""
from .base import BaseRule
from .registry import RuleRegistry

__all__ = ["BaseRule", "RuleRegistry"]
