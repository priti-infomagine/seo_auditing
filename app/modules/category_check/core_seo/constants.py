"""
Constants for the Core SEO crawler pipeline.

Default values, SSRF blocked networks, tracking parameters,
SEO category weights, and grade thresholds.
"""

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_DEPTH = 3
DEFAULT_CONCURRENCY = 5
DEFAULT_BROWSER_CONCURRENCY = 3
DEFAULT_TIMEOUT = 30.0
DEFAULT_BROWSER_TIMEOUT = 30.0
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_CRAWL_DELAY_MS = 0

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"

MAX_URL_LENGTH = 2048

# ── SSRF Protection ──────────────────────────────────────────────────
BLOCKED_IP_NETWORKS = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.88.99.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]

BLOCKED_HOST_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".lan",
    ".corp",
    ".home",
)

BLOCKED_HOSTS = {
    "localhost",
}

# ── Tracking Parameters to Strip ─────────────────────────────────────
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_referrer",
    "utm_site",
    "gclid",
    "fbclid",
    "igshid",
    "mc_eid",
    "mc_cid",
    "msclkid",
    "twclid",
    "ttd_pid",
    "tt_click_id",
    "li_fat",
    "_ga",
    "_gid",
    "_gcl_au",
    "fbp",
    "fbc",
    "s_k",
    "s_iv",
    "mkt_tok",
    "ref",
    "source",
    "cmpid",
    "ref_src",
}

# ── SEO Category Weights ────────────────────────────────────────────────
ON_PAGE_WEIGHT = 0.65
TECHNICAL_WEIGHT = 0.35

CATEGORY_WEIGHTS = {
    "on_page": ON_PAGE_WEIGHT,
    "technical": TECHNICAL_WEIGHT,
    "content": 0.0,
    "links": 0.0,
    "images": 0.0,
    "schema": 0.0,
    "social": 0.0,
    "security": 0.0,
    "accessibility": 0.0,
    "performance": 0.0,
}

# ── Grade Thresholds ──────────────────────────────────────────────────
GRADE_THRESHOLDS = {
    "A+": 95,
    "A": 90,
    "B+": 85,
    "B": 80,
    "C+": 75,
    "C": 70,
    "D": 60,
    "E": 50,
    "F": 0,
}

# ── SEO Check Thresholds ──────────────────────────────────────────────
MIN_WORDS_GOOD = 300
MIN_WORDS_ACCEPTABLE = 100
MIN_INTERNAL_LINKS = 1
MIN_H1_COUNT = 1
MAX_H1_COUNT = 1
MIN_TITLE_LENGTH = 30
MAX_TITLE_LENGTH = 70
MIN_META_DESC_LENGTH = 120
MAX_META_DESC_LENGTH = 165

# ── Category Order ────────────────────────────────────────────────────
CATEGORY_ORDER = {
    "on_page": 1,
    "technical": 2,
    "content": 3,
    "links": 4,
    "images": 5,
    "schema": 6,
    "social": 7,
    "security": 8,
    "accessibility": 9,
    "performance": 10,
}

__all__ = [
    "BLOCKED_HOSTS",
    "BLOCKED_HOST_SUFFIXES",
    "BLOCKED_IP_NETWORKS",
    "CATEGORY_ORDER",
    "CATEGORY_WEIGHTS",
    "DEFAULT_ACCEPT_LANGUAGE",
    "DEFAULT_BROWSER_CONCURRENCY",
    "DEFAULT_BROWSER_TIMEOUT",
    "DEFAULT_CONCURRENCY",
    "DEFAULT_CRAWL_DELAY_MS",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_REQUEST_TIMEOUT",
    "DEFAULT_TIMEOUT",
    "DEFAULT_USER_AGENT",
    "GRADE_THRESHOLDS",
    "MAX_H1_COUNT",
    "MAX_META_DESC_LENGTH",
    "MAX_TITLE_LENGTH",
    "MAX_URL_LENGTH",
    "MIN_H1_COUNT",
    "MIN_INTERNAL_LINKS",
    "MIN_META_DESC_LENGTH",
    "MIN_TITLE_LENGTH",
    "MIN_WORDS_ACCEPTABLE",
    "MIN_WORDS_GOOD",
    "ON_PAGE_WEIGHT",
    "TECHNICAL_WEIGHT",
    "TRACKING_PARAMS",
]
