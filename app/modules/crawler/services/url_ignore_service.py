"""
UrlIgnoreService — DB-backed URL pattern matching engine.

Loads ignore patterns from the url_ignore_patterns table, matches URLs against them
by scope (global, performance, accessibility, bestpractices, seo), and provides
methods to check runtime conditions and log skip records.
"""
import re
from typing import Dict, List, Optional, Tuple, Set
from urllib.parse import urlparse, parse_qs
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.#loggger import #loggger
from app.modules.config.models.url_ignore_pattern import UrlIgnorePattern


_VALID_MATCH_TYPES = {"path", "prefix", "extension", "query_param", "regex", "scheme", "host"}
_VALID_SCOPES = {"global", "performance", "accessibility", "bestpractices", "seo"}


class UrlIgnoreService:
    """
    Loads URL ignore patterns from the database and matches URLs against them.

    Patterns are loaded once per scope and cached in-memory for the duration
    of a crawl or audit phase. The service provides:
      - check_url(url, scope) -> (is_ignored, reason_code, description)
      - check_url_all_scopes(url) -> dict[scope, (is_ignored, reason, description)]
      - log_skip(async) -> persists a skip record
      - check_runtime_conditions(crawl_page) -> (is_skipped, reason_code)
    """

    MAX_URL_LENGTH = 2000
    MAX_QUERY_PARAMS = 5
    MAX_REDIRECT_CHAIN = 5

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self._pattern_cache: Dict[str, List[UrlIgnorePattern]] = {}
        self._regex_cache: Dict[str, re.Pattern] = {}

    async def load_patterns(
        self,
        db: AsyncSession,
        scope: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> List[UrlIgnorePattern]:
        """Load active patterns for a single scope or multiple scopes."""
        target_scopes = scopes if scopes else ([scope] if scope else [])
        for s in target_scopes:
            if s not in self._pattern_cache:
                result = await db.execute(
                    select(UrlIgnorePattern).where(
                        UrlIgnorePattern.record_type == "pattern",
                        UrlIgnorePattern.scope == s,
                        UrlIgnorePattern.is_active == True,
                    ).order_by(UrlIgnorePattern.sort_order, UrlIgnorePattern.id)
                )
                patterns = list(result.scalars().all())
                self._pattern_cache[s] = patterns
                for p in patterns:
                    if p.match_type == "regex" and p.pattern:
                        try:
                            self._regex_cache[p.pattern] = re.compile(p.pattern, re.IGNORECASE)
                        except re.error as e:
                            #loggger.warning(f"Invalid regex pattern '{p.pattern}': {e}")
        all_patterns: List[UrlIgnorePattern] = []
        for s in target_scopes:
            all_patterns.extend(self._pattern_cache.get(s, []))
        return all_patterns

    def check_url(
        self,
        url: str,
        scope: Optional[str] = None,
        all_loaded: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a URL matches any pattern for the given scope.

        Returns:
            (is_ignored, reason_code, description) — reason_code/description are None if not ignored.
            When all_loaded=True, the third element is the matching scope name.
        """
        parsed = urlparse(url)
        path = parsed.path.lower() if parsed.path else ""
        scheme = parsed.scheme.lower() if parsed.scheme else ""
        host = parsed.netloc.lower() if parsed.netloc else ""
        query = parsed.query or ""
        query_params = self._extract_param_names(query)

        if all_loaded:
            for s, patterns in self._pattern_cache.items():
                for p in patterns:
                    if p.match_type is None:
                        continue
                    if self._matches(p, parsed, path, scheme, host, query, query_params, url):
                        return True, p.reason, s
            return False, None, None

        if scope not in self._pattern_cache:
            return False, None, None

        for p in self._pattern_cache[scope]:
            if p.match_type is None:
                continue
            if self._matches(p, parsed, path, scheme, host, query, query_params, url):
                return True, p.reason, p.description

        return False, None, None

    def check_url_all_scopes(self, url: str) -> Dict[str, Tuple[bool, Optional[str], Optional[str]]]:
        """Check a URL against all scopes at once."""
        result = {}
        for scope in _VALID_SCOPES:
            result[scope] = self.check_url(url, scope)
        return result

    def check_runtime_conditions(self, crawl_page) -> Tuple[bool, Optional[str]]:
        """
        Check runtime conditions that can only be determined from crawled data.

        Uses CrawlPage fields: status_code, is_redirect, url, normalized_url, path.
        Returns (is_skipped, reason_code).
        """
        if not crawl_page:
            return False, None

        if getattr(crawl_page, "is_redirect", False):
            return True, "redirect_source"

        status_code = getattr(crawl_page, "status_code", None)
        if status_code is not None and status_code >= 400:
            return True, "error_page"

        url = getattr(crawl_page, "normalized_url", "") or getattr(crawl_page, "url", "")
        if url:
            if len(url) > self.MAX_URL_LENGTH:
                return True, "url_too_long"
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if len(params) > self.MAX_QUERY_PARAMS:
                return True, "too_many_params"

        return False, None

    def _matches(
        self,
        pattern: UrlIgnorePattern,
        parsed_url,
        path: str,
        scheme: str,
        host: str,
        query: str,
        query_params: List[str],
        full_url: str,
    ) -> bool:
        """Match a single pattern against URL components."""
        if pattern.match_type is None or pattern.pattern is None:
            return False

        mt = pattern.match_type

        if mt == "path":
            return path == pattern.pattern.lower()

        if mt == "prefix":
            return path.startswith(pattern.pattern.lower())

        if mt == "extension":
            return path.endswith(pattern.pattern.lower())

        if mt == "query_param":
            param_matcher = pattern.pattern.lower()
            for param_name in query_params:
                param_lower = param_name.lower()
                if param_lower == param_matcher:
                    return True
                if param_matcher.endswith("_") and param_lower.startswith(param_matcher):
                    return True
            return False

        if mt == "regex":
            if pattern.pattern in self._regex_cache:
                regex = self._regex_cache[pattern.pattern]
            else:
                try:
                    regex = re.compile(pattern.pattern, re.IGNORECASE)
                    self._regex_cache[pattern.pattern] = regex
                except re.error:
                    return False
            return bool(regex.search(full_url))

        if mt == "scheme":
            return scheme == pattern.pattern.lower()

        if mt == "host":
            return host == pattern.pattern.lower()

        return False

    def _extract_param_names(self, query: str) -> List[str]:
        """Extract parameter names from a query string."""
        if not query:
            return []
        return [part.split("=")[0] for part in query.split("&") if "=" in part]

    async def log_skip(
        self,
        audit_id: UUID,
        url: str,
        normalized_url: str,
        reason: str,
        scope: str,
        matched_pattern_id: Optional[UUID] = None,
    ) -> Optional[UrlIgnorePattern]:
        """Insert a skip record (record_type='skip') into the url_ignore_patterns table."""
        if not self.db:
            #loggger.warning("log_skip called without db session")
            return None

        from app.modules.config.repositories.url_ignore_repository import UrlIgnorePatternRepository
        repo = UrlIgnorePatternRepository(self.db)
        return await repo.log_skip(
            audit_id=audit_id,
            url=url,
            normalized_url=normalized_url,
            reason=reason,
            scope=scope,
            matched_pattern_id=matched_pattern_id,
        )

    def clear_cache(self) -> None:
        """Clear all cached patterns and compiled regexes."""
        self._pattern_cache.clear()
        self._regex_cache.clear()

    @staticmethod
    def get_all_pattern_scopes() -> Set[str]:
        """Return all valid pattern scopes."""
        return set(_VALID_SCOPES)