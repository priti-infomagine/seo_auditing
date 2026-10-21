"""Checks package — concrete SEO rule implementations (18 rules)."""
from .canonical_rules import (
    CanonicalAndNoindexConflictRule,
    CanonicalHeaderValidationRule,
    CanonicalLoopDetectionRule,
    CanonicalNotPointingToHomepageRule,
    CanonicalProtocolMatchRule,
    CanonicalURLPresentRule,
    CanonicalURLValidRule,
    ConflictingCanonicalURLsRule,
)
from .heading_rules import H1TagPresentRule, SingleH1TagRule
from .meta_rules import MetaDescriptionLengthRule, MetaDescriptionPresentRule
from .technical_rules import (
    FaviconPresentRule,
    NoSnippetBlockingRule,
    RobotsMetaDirectivesRule,
    ViewportMetaTagRule,
)
from .title_rules import TitleTagLengthRule, TitleTagPresentRule

__all__ = [
    "CanonicalAndNoindexConflictRule",
    "CanonicalHeaderValidationRule",
    "CanonicalLoopDetectionRule",
    "CanonicalNotPointingToHomepageRule",
    "CanonicalProtocolMatchRule",
    "CanonicalURLPresentRule",
    "CanonicalURLValidRule",
    "ConflictingCanonicalURLsRule",
    "FaviconPresentRule",
    "H1TagPresentRule",
    "MetaDescriptionLengthRule",
    "MetaDescriptionPresentRule",
    "NoSnippetBlockingRule",
    "RobotsMetaDirectivesRule",
    "SingleH1TagRule",
    "TitleTagLengthRule",
    "TitleTagPresentRule",
    "ViewportMetaTagRule",
]
