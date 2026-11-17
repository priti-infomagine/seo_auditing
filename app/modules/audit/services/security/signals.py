"""Site-level security signals collected once per audit."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass(slots=True)
class TLSSignal:
    hostname: str
    port: int = 443
    tls_version: Optional[str] = None
    cipher: Optional[str] = None
    certificate_valid: bool = False
    certificate_issuer: Optional[str] = None
    certificate_expiry: Optional[datetime] = None
    certificate_san: List[str] = field(default_factory=list)
    chain_trusted: bool = False
    error: Optional[str] = None
    tested_tls10: Optional[bool] = None
    tested_tls11: Optional[bool] = None


@dataclass(slots=True)
class HTTPRedirectSignal:
    http_url: str
    final_url: str
    redirect_chain: List[dict] = field(default_factory=list)
    is_permanent_redirect: bool = False
    http_loads_directly: bool = False
    certificate_error: bool = False
    error: Optional[str] = None


@dataclass(slots=True)
class SiteSignals:
    base_url: str
    hostname: str
    tls: Optional[TLSSignal] = None
    http_redirect: Optional[HTTPRedirectSignal] = None
    hsts_header: Optional[str] = None
    hsts_max_age: Optional[int] = None
    hsts_include_subdomains: bool = False
    hsts_preload: bool = False
    security_headers: dict = field(default_factory=dict)
    collected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())