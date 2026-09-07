"""
Shared exception types for all non-auth modules of the SSEO Analyzer.

These exceptions follow a fault-tolerant design:
- Non-fatal errors (parser failures, rule failures, missing data) are caught
  at the call site and logged, allowing the pipeline to continue.
- Fatal system-level errors (database unreachable, crawl not found) propagate
  to fail the entire operation.

Auth module is explicitly excluded from this pattern — auth failures
should raise 401/403.
"""


class SSEOAnalyzerError(Exception):
    """Base exception for all non-auth modules of the SSEO Analyzer."""


class ParserError(SSEOAnalyzerError):
    """Raised when page parsing fails (non-fatal — pipeline continues)."""


class RuleEvaluationError(SSEOAnalyzerError):
    """Raised when a single rule evaluation fails (non-fatal)."""


class ScoringError(SSEOAnalyzerError):
    """Raised when score calculation fails for a page or project (non-fatal)."""


class DatabaseError(SSEOAnalyzerError):
    """Raised on database operation failures (system-level)."""


__all__ = [
    "SSEOAnalyzerError",
    "ParserError",
    "RuleEvaluationError",
    "ScoringError",
    "DatabaseError",
]
