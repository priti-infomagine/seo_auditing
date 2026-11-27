"""
URL Structure Shared Utilities.
Common parsing, record building, and helper functions for URL structure rules.
"""
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Dict, List
from urllib.parse import SplitResult, parse_qsl, unquote, urlsplit

from app.modules.rule_engine.config.url_structure_config import UrlStructureConfig


ASSET_EXTS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico',
    '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.eot',
    '.pdf', '.zip', '.mp4', '.mp3', '.webm', '.ogg', '.avi',
    '.mov', '.woff', '.woff2'
}
MAX_URL_LEN = 4096


@dataclass
class UrlRecord:
    """Normalized URL record for rule evaluation."""
    url: str
    raw: str
    scope: str
    parts: SplitResult
    anchor: str = ''
    is_internal: bool = True

    @property
    def path(self) -> str:
        return self.parts.path

    @property
    def query(self) -> str:
        return self.parts.query

    @cached_property
    def raw_parts(self) -> SplitResult:
        return urlsplit(self.raw)

    @cached_property
    def is_asset(self) -> bool:
        last = self.path.rsplit('/', 1)[-1].lower()
        return '.' in last and '.' + last.rsplit('.', 1)[-1] in ASSET_EXTS

    @cached_property
    def segments(self) -> List[str]:
        return [s for s in self.path.split('/') if s]

    @cached_property
    def slug(self) -> str:
        if not self.segments:
            return ''
        last = unquote(self.segments[-1])
        return last.rsplit('.', 1)[0] if '.' in last else last


def tokens(text: str) -> List[str]:
    """Split text into lowercase tokens, Unicode-aware."""
    # Split on separators and remove punctuation
    return [t for t in re.split(r'[-_+ ./!@#$%^&*()]+', text.lower()) if t]


def looks_random(value: str) -> bool:
    """Check if a string looks like a random session identifier."""
    if len(value) < 16:
        return False
    if not all(c.isalnum() or c in '-_' for c in value):
        return False
    has_digit = any(c.isdigit() for c in value)
    has_alpha = any(c.isalpha() for c in value)
    return has_digit and has_alpha


def build_records(data: Dict[str, Any], cfg: UrlStructureConfig) -> List[UrlRecord]:
    """
    Build UrlRecord list from audit data.
    
    Supports two data formats:
    1. RuleEvaluatorService format: url.final_url, url.normalized_url, links.internal_links with absolute_url
    2. ScorerService format: url.path, url.query, url.domain, url.https, links as a list
    
    Page URL: final_url > normalized_url > url > reconstructed from domain+path
    Links: absolute_url for structure, href (raw) for encoding checks
    Deduplicates on URL without fragment.
    Caps at max_links.
    """
    page = data.get('url') or {}
    
    # Try RuleEvaluatorService format first
    page_url = page.get('final_url') or page.get('normalized_url') or page.get('url')
    
    # Fallback to ScorerService format: reconstruct from components
    if not page_url:
        domain = page.get('domain', '')
        path = page.get('path', '')
        if domain and path:
            scheme = 'https' if page.get('https') else 'http'
            page_url = f'{scheme}://{domain}{path}'
            if page.get('query'):
                page_url += f'?{page["query"]}'
    
    records: List[UrlRecord] = []
    seen: set = set()
    
    def add(
        url: str,
        raw: str,
        scope: str,
        anchor: str = '',
        is_internal: bool = True,
    ):
        if not url or len(url) > MAX_URL_LEN:
            return
        try:
            parts = urlsplit(url)
            if parts.scheme not in ('http', 'https'):
                return
            key = parts._replace(fragment='').geturl()
            if key in seen:
                return
            rec = UrlRecord(url, raw or url, scope, parts, anchor, is_internal)
            rec.raw_parts  # Force parse to catch bad hrefs early
        except ValueError:
            return
        seen.add(key)
        records.append(rec)
    
    if page_url:
        add(page_url, page_url, 'page')
    
    # Handle links - try internal_links first (RuleEvaluatorService format)
    links_data = data.get('links') or {}
    if isinstance(links_data, dict):
        links = (links_data.get('internal_links') or [])[:cfg.max_links]
    else:
        # ScorerService format: links is a list
        links = (links_data or [])[:cfg.max_links]
    
    for link in links:
        if not isinstance(link, dict):
            continue
        abs_url = link.get('absolute_url') or link.get('url')
        raw_href = link.get('href') or link.get('raw_href')
        anchor_text = link.get('text') or ''
        if abs_url:
            is_internal = link.get('is_internal')
            if is_internal is None:
                is_internal = not (
                    link.get('is_external')
                    or link.get('link_type') == 'external'
                )
            add(
                abs_url,
                raw_href or abs_url,
                'link',
                anchor_text,
                bool(is_internal),
            )
    
    return records


def get_page_text_data(data: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extract title and H1 tokens for slug quality checks."""
    basic = data.get('basic') or {}
    headings = data.get('headings') or {}
    
    title = basic.get('title', '')
    h1_list = headings.get('h1', [])
    h1 = h1_list[0] if h1_list else ''
    lang = basic.get('language', '').lower().split('-')[0] if basic.get('language') else 'en'
    
    return {
        'title_tokens': tokens(title),
        'h1_tokens': tokens(h1),
        'lang': lang,
    }