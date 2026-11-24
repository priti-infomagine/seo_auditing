"""
URL Structure Configuration.
Centralized configuration for URL structure rules with environment override support.
"""
import os
from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class UrlStructureConfig:
    enabled: bool = True
    max_links: int = 500
    max_reported: int = 10
    link_saturation: float = 0.25
    stop_words: FrozenSet[str] = frozenset({
        'the', 'and', 'or', 'for', 'in', 'on', 'to', 'a', 'an', 'of',
        'with', 'by', 'from', 'as', 'at', 'is', 'it', 'be', 'this', 'that'
    })
    stop_word_langs: FrozenSet[str] = frozenset({'en'})
    session_strong: FrozenSet[str] = frozenset({
        'jsessionid', 'phpsessid', 'sessionid', 'session_id', 'sessid',
        'aspsessionid', 'cfid', 'cftoken'
    })
    session_guarded: FrozenSet[str] = frozenset({
        'sid', 'token', 'session', 'sessionkey'
    })
    tracking_exact: FrozenSet[str] = frozenset({
        'gclid', 'fbclid', 'msclkid', 'dclid', 'gbraid', 'wbraid',
        'yclid', 'ttclid', 'twclid', 'igshid', 'mc_cid', 'mc_eid',
        '_ga', '_gl'
    })
    tracking_prefixes: tuple = ('utm_', 'hsa_', 'pk_', 'mtm_')
    search_segments: FrozenSet[str] = frozenset({
        'search', 'results', 'search-results', 'searchresults'
    })
    search_params: FrozenSet[str] = frozenset({
        's', 'q', 'query', 'search', 'search_query', 'keyword',
        'keywords', 'searchterm'
    })
    total_len_info: int = 200
    path_len_info: int = 100
    total_len_warn: int = 2000
    max_params: int = 5


def _parse_frozenset(env_value: str) -> FrozenSet[str]:
    if not env_value:
        return frozenset()
    return frozenset(v.strip().lower() for v in env_value.split(',') if v.strip())


def get_url_structure_config() -> UrlStructureConfig:
    """Load configuration from environment with defaults."""
    return UrlStructureConfig(
        enabled=os.getenv('URL_STRUCTURE_ENABLED', 'true').lower() == 'true',
        max_links=int(os.getenv('URL_STRUCTURE_MAX_LINKS', '500')),
        max_reported=int(os.getenv('URL_STRUCTURE_MAX_REPORTED', '10')),
        link_saturation=float(os.getenv('URL_STRUCTURE_LINK_SATURATION', '0.25')),
        stop_words=_parse_frozenset(os.getenv('URL_STRUCTURE_STOP_WORDS', ''))
        or frozenset({
            'the', 'and', 'or', 'for', 'in', 'on', 'to', 'a', 'an', 'of',
            'with', 'by', 'from', 'as', 'at', 'is', 'it', 'be', 'this', 'that'
        }),
        stop_word_langs=_parse_frozenset(os.getenv('URL_STRUCTURE_STOP_WORD_LANGS', 'en'))
        or frozenset({'en'}),
        session_strong=_parse_frozenset(os.getenv('URL_STRUCTURE_SESSION_STRONG', ''))
        or frozenset({
            'jsessionid', 'phpsessid', 'sessionid', 'session_id', 'sessid',
            'aspsessionid', 'cfid', 'cftoken'
        }),
        session_guarded=_parse_frozenset(os.getenv('URL_STRUCTURE_SESSION_GUARDED', ''))
        or frozenset({'sid', 'token', 'session', 'sessionkey'}),
        tracking_exact=_parse_frozenset(os.getenv('URL_STRUCTURE_TRACKING_EXACT', ''))
        or frozenset({
            'gclid', 'fbclid', 'msclkid', 'dclid', 'gbraid', 'wbraid',
            'yclid', 'ttclid', 'twclid', 'igshid', 'mc_cid', 'mc_eid',
            '_ga', '_gl'
        }),
        tracking_prefixes=tuple(
            os.getenv('URL_STRUCTURE_TRACKING_PREFIXES', 'utm_,hsa_,pk_,mtm_').split(',')
        ),
        search_segments=_parse_frozenset(os.getenv('URL_STRUCTURE_SEARCH_SEGMENTS', ''))
        or frozenset({'search', 'results', 'search-results', 'searchresults'}),
        search_params=_parse_frozenset(os.getenv('URL_STRUCTURE_SEARCH_PARAMS', ''))
        or frozenset({'s', 'q', 'query', 'search', 'search_query', 'keyword', 'keywords', 'searchterm'}),
        total_len_info=int(os.getenv('URL_STRUCTURE_TOTAL_LEN_INFO', '200')),
        path_len_info=int(os.getenv('URL_STRUCTURE_PATH_LEN_INFO', '100')),
        total_len_warn=int(os.getenv('URL_STRUCTURE_TOTAL_LEN_WARN', '2000')),
        max_params=int(os.getenv('URL_STRUCTURE_MAX_PARAMS', '5')),
    )