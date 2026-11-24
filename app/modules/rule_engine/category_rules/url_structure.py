"""
URL Structure Category Rules.
15 rules evaluating URL cleanliness, readability, and SEO best practices.
"""
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, unquote

from app.modules.rule_engine.config.url_structure_config import UrlStructureConfig, get_url_structure_config
from app.modules.rule_engine.category_rules.url_structure_utils import (
    ASSET_EXTS, MAX_URL_LEN, UrlRecord, build_records, get_page_text_data,
    looks_random, tokens
)
from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class UrlPatternRule(BaseRule):
    """Base class for URL structure rules."""
    category = 'url_structure'
    severity = Severity.WARNING
    skip_assets = False
    recommendation = ''
    pass_message = ''
    fail_label = ''

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict[str, Any]) -> Optional[Dict]:
        """Return evidence dict if issue found, else None."""
        raise NotImplementedError

    def result_severity(self, issues: List[Dict]) -> Severity:
        return self.severity

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        cfg = get_url_structure_config()
        if not cfg.enabled:
            return []
        records = build_records(data, cfg)
        if not records:
            return []
        
        issues = []
        for rec in records:
            if self.skip_assets and rec.is_asset:
                continue
            found = self.check(rec, cfg, data)
            if found:
                issues.append({'url': rec.url, 'scope': rec.scope, **found})
        
        links_checked = sum(
            1 for r in records 
            if r.scope == 'link' and not (self.skip_assets and r.is_asset)
        )
        page_hit = any(i['scope'] == 'page' for i in issues)
        link_hits = sum(1 for i in issues if i['scope'] == 'link')
        
        if not issues:
            return [self._create_result(
                passed=True, message=self.pass_message,
                severity=Severity.PASSED, score_impact=0
            )]
        
        sev = self.result_severity(issues)
        return [self._create_result(
            passed=False,
            message=f'{len(issues)} of {len(records)} URLs {self.fail_label}',
            severity=sev, score_impact=0,
            recommendation=self.recommendation,
            data={
                'page_url_affected': page_hit,
                'affected_count': len(issues),
                'checked_count': len(records),
                'truncated': len(records) >= cfg.max_links,
                'affected_urls': issues[:cfg.max_reported]
            }
        )]


# ================================================================
# Rule 001: No Double Slashes in Path
# ================================================================
class NoDoubleSlashes(UrlPatternRule):
    rule_id = 'url_structure_001'
    name = 'No Double Slashes in Path'
    severity = Severity.WARNING
    fail_label = 'contain double slashes in the path'
    pass_message = 'No double slashes in any URL path'
    recommendation = 'Remove empty path segments and 301 redirect the old URL to the clean one.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        return {'path': rec.path} if '//' in rec.path else None


# ================================================================
# Rule 002: No Internal Search URLs
# ================================================================
class NoInternalSearchUrls(UrlPatternRule):
    rule_id = 'url_structure_002'
    name = 'No Internal Search URLs'
    severity = Severity.INFO
    fail_label = 'appear to be internal search result pages'
    pass_message = 'No internal search URLs detected'
    recommendation = 'Block search result pages in robots.txt or use noindex. They create near-infinite low-value URLs.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        for seg in rec.segments:
            if seg.lower() in cfg.search_segments:
                return {'path': rec.path, 'matched_segment': seg}
        for k, _ in parse_qsl(rec.query, keep_blank_values=True):
            if k.lower() in cfg.search_params:
                return {'path': rec.path, 'matched_param': k}
        return None


# ================================================================
# Rule 003: No Raw Non-ASCII Characters
# ================================================================
class NoRawNonAscii(UrlPatternRule):
    rule_id = 'url_structure_003'
    name = 'No Unencoded Non-ASCII Characters'
    severity = Severity.INFO
    skip_assets = True
    fail_label = 'contain unencoded non-ASCII characters'
    pass_message = 'All URLs properly percent-encode non-ASCII characters'
    recommendation = 'Percent-encode non-ASCII characters in href attributes. Use UTF-8 encoding for IDN domains.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        raw_path = rec.raw_parts.path
        raw_query = rec.raw_parts.query
        for ch in raw_path + raw_query:
            if ord(ch) > 0x7F:
                return {'raw_path': raw_path, 'raw_query': raw_query, 'char': ch, 'codepoint': hex(ord(ch))}
        return None


# ================================================================
# Rule 004: No Repetitive Path Segments
# ================================================================
def repeating_block(segs: List[str]) -> Optional[tuple]:
    """Find consecutive repeating block of segments. Returns (block_length, block_list) or None."""
    n = len(segs)
    for k in range(1, n // 2 + 1):
        for i in range(0, n - 2 * k + 1):
            a, b = segs[i:i + k], segs[i + k:i + 2 * k]
            if a == b and not all(s.isdigit() for s in a):
                return k, a
    return None


class NoRepetitiveSegments(UrlPatternRule):
    rule_id = 'url_structure_004'
    name = 'No Repetitive Path Segments'
    severity = Severity.WARNING
    fail_label = 'contain repeated path segments'
    pass_message = 'No repeated path segments'
    recommendation = 'Fix broken relative links (use root-relative paths) and remove duplicated folders.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        hit = repeating_block([s.lower() for s in rec.segments])
        if not hit:
            return None
        k, block = hit
        return {'segments': block, 'block_length': k, 'likely_trap': k >= 2}


# ================================================================
# Rule 005: No Session IDs in URL
# ================================================================
class NoSessionIds(UrlPatternRule):
    rule_id = 'url_structure_005'
    name = 'No Session IDs in URL'
    severity = Severity.CRITICAL
    fail_label = 'contain session identifiers'
    pass_message = 'No session identifiers found in URLs'
    recommendation = 'Move session state to cookies. Session IDs create unlimited duplicate URLs.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        hits = []
        for k, v in parse_qsl(rec.query, keep_blank_values=True):
            kl = k.lower()
            if kl in cfg.session_strong or kl.startswith('aspsessionid'):
                hits.append({'param': k, 'confidence': 'strong'})
            elif kl in cfg.session_guarded and looks_random(v):
                hits.append({'param': k, 'confidence': 'guarded'})
        m = re.search(r';(jsessionid|phpsessid|sessionid)=', rec.path, re.I)
        if m:
            hits.append({'param': m.group(1), 'confidence': 'strong', 'in': 'path'})
        return {'hits': hits} if hits else None

    def result_severity(self, issues: List[Dict]) -> Severity:
        strong = any(
            h['confidence'] == 'strong' 
            for i in issues 
            for h in i.get('hits', [])
        )
        return Severity.CRITICAL if strong else Severity.WARNING


# ================================================================
# Rule 006: No Spaces in URL
# ================================================================
class NoSpacesInUrl(UrlPatternRule):
    rule_id = 'url_structure_006'
    name = 'No Spaces in URL'
    severity = Severity.WARNING
    fail_label = 'contain spaces in the path'
    pass_message = 'No spaces found in URL paths'
    recommendation = 'Replace spaces with hyphens. Spaces encode as %20 which is hard to read and share.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        raw_path = rec.raw_parts.path
        if ' ' in raw_path or '%20' in raw_path:
            return {'raw_path': raw_path}
        return None


# ================================================================
# Rule 007: No Stop Words in URL
# ================================================================
class NoStopWords(UrlPatternRule):
    rule_id = 'url_structure_007'
    name = 'No Stop Words in URL Slug'
    severity = Severity.INFO
    skip_assets = True
    fail_label = 'contain stop words in the slug'
    pass_message = 'No excessive stop words in URL slugs'
    recommendation = 'Remove stop words from new URL slugs. Keep slugs concise and keyword-focused. Do not change established URLs.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        if rec.scope == 'link':
            return None
        text_data = get_page_text_data(data)
        if text_data['lang'] not in cfg.stop_word_langs:
            return None
        slug_tokens = tokens(rec.slug)
        if not slug_tokens:
            return None
        stop_count = sum(1 for t in slug_tokens if t in cfg.stop_words)
        if stop_count >= 2 or (stop_count >= 1 and len(slug_tokens) >= 5):
            return {
                'slug': rec.slug,
                'tokens': slug_tokens,
                'stop_words_found': [t for t in slug_tokens if t in cfg.stop_words]
            }
        return None


# ================================================================
# Rule 008: No Tracking Parameters
# ================================================================
class NoTrackingParameters(UrlPatternRule):
    rule_id = 'url_structure_008'
    name = 'No Tracking Parameters'
    severity = Severity.WARNING
    fail_label = 'contain tracking parameters'
    pass_message = 'No tracking parameters found in URLs'
    recommendation = 'Remove tracking parameters from internal links. They create duplicate URLs and break analytics attribution.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        # Only flag tracking parameters on INTERNAL links (page URL or internal links)
        # External links with tracking params don't affect our site's crawl budget
        if rec.scope == "link" and not rec.is_internal:
            return None
        
        found = []
        for k, v in parse_qsl(rec.query, keep_blank_values=True):
            kl = k.lower()
            if kl in cfg.tracking_exact or any(kl.startswith(p) for p in cfg.tracking_prefixes):
                found.append({'param': k, 'value': v[:50]})
        if found:
            return {'params': found}
        return None

    def result_severity(self, issues: List[Dict]) -> Severity:
        link_hits = any(i['scope'] == 'link' for i in issues)
        return Severity.WARNING if link_hits else Severity.INFO


# ================================================================
# Rule 009: No Underscores in URL
# ================================================================
class NoUnderscores(UrlPatternRule):
    rule_id = 'url_structure_009'
    name = 'No Underscores in URL Path'
    severity = Severity.WARNING
    skip_assets = True
    fail_label = 'contain underscores in the path'
    pass_message = 'All URL paths use hyphens as word separators'
    recommendation = 'Use hyphens instead of underscores. Hyphens are the recommended word separator for SEO.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        path = unquote(rec.path)
        for seg in path.split('/'):
            if seg.startswith('_'):
                continue
            if '_' in seg:
                return {'path': rec.path, 'segment': seg}
        return None


# ================================================================
# Rule 010: No Uppercase in URL
# ================================================================
class NoUppercase(UrlPatternRule):
    rule_id = 'url_structure_010'
    name = 'No Uppercase in URL Path'
    severity = Severity.WARNING
    skip_assets = True
    fail_label = 'contain uppercase letters in the path'
    pass_message = 'All URL paths are lowercase'
    recommendation = 'Use lowercase paths and 301 redirect mixed-case URLs. Paths are case-sensitive on many servers.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        path = re.sub(r'%[0-9A-Fa-f]{2}', '', rec.path)
        for ch in path:
            if ch.isupper():
                return {'path': rec.path, 'char': ch}
        return None


# ================================================================
# Rule 011: URL Length
# ================================================================
class UrlLength(UrlPatternRule):
    rule_id = 'url_structure_011'
    name = 'URL Length'
    severity = Severity.INFO
    fail_label = 'exceed recommended length'
    pass_message = 'All URLs within recommended length limits'
    recommendation = 'Keep URLs under 200 characters total and 100 characters for the path. Very long URLs risk truncation and are hard to share.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        decoded_url = unquote(rec.url)
        decoded_path = unquote(rec.path)
        
        if len(decoded_url) > cfg.total_len_warn:
            return {
                'total_length': len(decoded_url),
                'path_length': len(decoded_path),
                'level': 'WARNING'
            }
        if len(decoded_url) > cfg.total_len_info or len(decoded_path) > cfg.path_len_info:
            return {
                'total_length': len(decoded_url),
                'path_length': len(decoded_path),
                'level': 'INFO'
            }
        return None

    def result_severity(self, issues: List[Dict]) -> Severity:
        has_warn = any(i.get('level') == 'WARNING' for i in issues)
        return Severity.WARNING if has_warn else Severity.INFO


# ================================================================
# Rule 012: URL Parameters
# ================================================================
class UrlParameters(UrlPatternRule):
    rule_id = 'url_structure_012'
    name = 'URL Parameters Count'
    severity = Severity.INFO
    fail_label = 'have too many query parameters'
    pass_message = 'All URLs have a reasonable number of query parameters'
    recommendation = 'Limit query parameters to 5 or fewer. Excessive parameters multiply crawlable URLs and complicate caching.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        params = parse_qsl(rec.query, keep_blank_values=True)
        if len(params) > cfg.max_params:
            return {
                'param_count': len(params),
                'params': [k for k, _ in params[:5]]
            }
        return None


# ================================================================
# Rule 013: Slug Quality
# ================================================================
class SlugQuality(UrlPatternRule):
    rule_id = 'url_structure_013'
    name = 'URL Slug Quality'
    severity = Severity.INFO
    skip_assets = True
    fail_label = 'have low-quality slugs'
    pass_message = 'URL slugs are descriptive and keyword-rich'
    recommendation = 'Use descriptive, keyword-rich slugs. Avoid numeric IDs, hashes, or parameter-only URLs for content pages.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        slug = rec.slug
        
        # Parameter-only detection (for page URL only) - check before empty slug return
        if rec.scope == 'page' and not slug and rec.query:
            for k, _ in parse_qsl(rec.query, keep_blank_values=True):
                if k.lower() in ('p', 'id', 'page_id', 'post_id'):
                    return {'slug': slug, 'query': rec.query, 'issue': 'parameter_only'}
        
        if not slug:
            return None
        
        # ID/hash detection
        if slug.isdigit():
            return {'slug': slug, 'issue': 'numeric_id'}
        if re.fullmatch(r'[0-9a-f]{16,}', slug, re.I):
            return {'slug': slug, 'issue': 'hash_like'}
        
        # Title/H1 overlap (page URL only)
        if rec.scope == 'page':
            text_data = get_page_text_data(data)
            ref_tokens = set(text_data['title_tokens'] + text_data['h1_tokens'])
            slug_toks = set(tokens(slug))
            if ref_tokens and not slug_toks & ref_tokens:
                return {
                    'slug': slug,
                    'issue': 'no_title_h1_overlap',
                    'slug_tokens': list(slug_toks),
                    'ref_tokens': list(ref_tokens)[:10]
                }
        return None


# ================================================================
# Rule 014: No Hash-Based Routing
# ================================================================
class NoHashRouting(UrlPatternRule):
    rule_id = 'url_structure_014'
    name = 'No Hash-Based Routing'
    severity = Severity.WARNING
    skip_assets = True
    fail_label = 'use hash-based routing'
    pass_message = 'No hash-based routing detected in internal links'
    recommendation = 'Use proper URL paths for content pages. Hash routes (/#/ or /#!/) are generally not crawled as separate pages.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        frag = rec.raw_parts.fragment
        if frag and (frag.startswith('/') or frag.startswith('!')):
            return {'fragment': frag, 'url': rec.raw}
        return None


# ================================================================
# Rule 015: Valid URL Encoding
# ================================================================
class ValidUrlEncoding(UrlPatternRule):
    rule_id = 'url_structure_015'
    name = 'Valid URL Encoding'
    severity = Severity.WARNING
    fail_label = 'have invalid or non-standard encoding'
    pass_message = 'All URLs use valid percent-encoding'
    recommendation = 'Fix malformed percent-encoding. Use valid UTF-8 percent-encoding. Avoid custom delimiters like ,,, : or leading [ in query strings.'

    def check(self, rec: UrlRecord, cfg: UrlStructureConfig, data: Dict) -> Optional[Dict]:
        raw = rec.raw
        
        # Lone % or invalid hex
        if re.search(r'%(?![0-9A-Fa-f]{2})', raw):
            return {'raw': raw, 'issue': 'invalid_percent_encoding'}
        
        # Decode and check UTF-8 validity
        try:
            decoded = unquote(raw)
            # Check for UTF-8 replacement characters (indicates invalid UTF-8)
            if '\ufffd' in decoded:
                return {'raw': raw, 'issue': 'non_utf8_decoded'}
        except UnicodeDecodeError:
            return {'raw': raw, 'issue': 'non_utf8_decoded'}
        
        # Custom delimiters in query (but allow simple flags like ?amp)
        query = rec.raw_parts.query
        if query:
            has_eq = '=' in query
            if not has_eq and re.search(r'[,;:\[\]]', query):
                return {'raw': raw, 'query': query, 'issue': 'custom_delimiters'}
            # Check for malformed repeated delimiters
            if re.search(r',,+|;{2,}|:{2,}', query):
                return {'raw': raw, 'query': query, 'issue': 'repeated_delimiters'}
        
        return None


# ================================================================
# Export all rules
# ================================================================
ALL_URL_STRUCTURE_RULES = [
    NoDoubleSlashes,
    NoInternalSearchUrls,
    NoRawNonAscii,
    NoRepetitiveSegments,
    NoSessionIds,
    NoSpacesInUrl,
    NoStopWords,
    NoTrackingParameters,
    NoUnderscores,
    NoUppercase,
    UrlLength,
    UrlParameters,
    SlugQuality,
    NoHashRouting,
    ValidUrlEncoding,
]

__all__ = ['ALL_URL_STRUCTURE_RULES'] + [r.__name__ for r in ALL_URL_STRUCTURE_RULES]