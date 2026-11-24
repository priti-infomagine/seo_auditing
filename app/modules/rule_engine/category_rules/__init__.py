"""
SEO Scoring Rules Package.

Rules are organized by category and evaluate parsed data to produce
RuleResult objects with score impacts.
"""
from app.modules.rule_engine.category_rules.url_structure import ALL_URL_STRUCTURE_RULES

__all__ = ['ALL_URL_STRUCTURE_RULES']