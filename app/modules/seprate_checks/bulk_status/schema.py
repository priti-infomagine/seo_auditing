from typing import Any, Literal, Optional
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


USER_AGENTS = {
    "chrome": (
        "Desktop Chrome",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36",
    ),
    "firefox": (
        "Desktop Firefox",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) "
        "Gecko/20100101 Firefox/131.0",
    ),
    "safari": (
        "Desktop Safari",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    ),
}


def normalize_http_url(value: str) -> str:
    """Validate and normalize an explicit HTTP(S) URL without changing its query."""
    raw = value.strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URLs must include a valid http:// or https:// hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs must not contain embedded credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL contains an invalid port") from exc

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


class RedirectCheckRequest(BaseModel):
    mode: Literal["urls", "domain"]
    urls: Optional[list[str]] = None
    domain: Optional[str] = None
    max_urls: int = Field(default=25, ge=1, le=500, alias="max_urls")
    user_agent: str = "chrome"

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_mode_inputs(self):
        self.user_agent = self.user_agent.strip().lower()
        if self.user_agent not in USER_AGENTS:
            raise ValueError(f"Unsupported user_agent; choose one of: {', '.join(USER_AGENTS)}")

        if self.mode == "urls":
            if self.domain is not None:
                raise ValueError("domain must not be provided when mode is 'urls'")
            if not self.urls:
                raise ValueError("urls must contain at least one URL when mode is 'urls'")
            if len(self.urls) > self.max_urls:
                raise ValueError("urls cannot contain more entries than max_urls")
            normalized_urls = []
            seen = set()
            for url in self.urls:
                normalized = normalize_http_url(url)
                if normalized not in seen:
                    normalized_urls.append(normalized)
                    seen.add(normalized)
            self.urls = normalized_urls
        else:
            if self.urls is not None:
                raise ValueError("urls must not be provided when mode is 'domain'")
            if not self.domain:
                raise ValueError("domain is required when mode is 'domain'")
            normalized_domain = normalize_http_url(self.domain)
            parsed = urlsplit(normalized_domain)
            if parsed.path not in ("", "/") or parsed.query:
                raise ValueError("domain mode accepts a site origin, not a page path or query")
            self.domain = normalized_domain
        return self


class RedirectHeader(BaseModel):
    name: str
    value: str
    ok: bool


class RedirectHop(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    status: Optional[int] = None
    status_text: Optional[str] = Field(default=None, alias="statusText")
    location: Optional[str] = None
    resolved: Optional[str] = None
    latency_ms: Optional[int] = Field(default=None, alias="latencyMs")
    headers: list[RedirectHeader] = Field(default_factory=list)


class RedirectResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input: str
    hops: list[RedirectHop] = Field(default_factory=list)
    redirects: int = 0
    final_url: Optional[str] = Field(default=None, alias="finalUrl")
    final_status: Optional[int] = Field(default=None, alias="finalStatus")
    error: Optional[str] = None


class UserAgentInfo(BaseModel):
    key: str
    label: str


class RedirectData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    results: list[RedirectResult] = Field(default_factory=list)
    checked: int = 0
    truncated: int = 0
    max_urls: int = Field(alias="maxUrls")
    user_agent: UserAgentInfo = Field(alias="userAgent")


class RedirectResponse(BaseModel):
    data: RedirectData
    cost: float


class RedirectCheckQueuedResponse(BaseModel):
    check_id: UUID
    task_id: str
    status: Literal["queued"]
    status_url: str


class RedirectCheckPollResponse(BaseModel):
    check_id: UUID
    task_id: str
    status: Literal["queued", "running", "retrying", "completed", "failed", "revoked"]
    result: Optional[RedirectResponse] = None
    error: Optional[str] = None
