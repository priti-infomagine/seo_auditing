# schemas/request.py
import ipaddress, re
from urllib.parse import urlsplit, urlunsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

MAX_PAGES_LIMIT = 10
MAX_URL_LENGTH = 2048
DEFAULT_PORTS = {"http": 80, "https": 443}
BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")
TLD_RE = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$")
SCHEME_LIKE = re.compile(r"^[a-z][a-z0-9+.\-]*:(?!\d)", re.I)   # javascript:, mailto:, but not site.com:8080

def _err(code: str, msg: str) -> PydanticCustomError:
    return PydanticCustomError(code, msg)

def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False

def normalize_url(raw: str) -> str:
    s = raw.strip()
    if not s:
        raise _err("url_empty", "URL is required")
    if len(s) > MAX_URL_LENGTH:
        raise _err("url_too_long", f"URL must be at most {MAX_URL_LENGTH} characters")
    if any(c.isspace() or ord(c) < 32 for c in s):
        raise _err("url_invalid_chars", "URL contains spaces or control characters")

    if "://" not in s:
        if SCHEME_LIKE.match(s):
            raise _err("url_scheme_not_allowed", "Only http and https URLs are allowed")
        s = "https://" + s                              # "infomagine.in" -> https://infomagine.in

    try:
        parts = urlsplit(s)
        port = parts.port
    except ValueError:
        raise _err("url_invalid", "URL is not valid")

    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise _err("url_scheme_not_allowed", "Only http and https URLs are allowed")
    if parts.username or parts.password:
        raise _err("url_credentials_not_allowed", "URLs with username or password are not allowed")
    if not parts.hostname:
        raise _err("url_invalid", "URL has no host")
    if port and port not in (80, 443):
        raise _err("url_port_not_allowed", "Only ports 80 and 443 are allowed")

    host = parts.hostname.rstrip(".").lower()
    if _is_ip(host):
        raise _err("url_ip_not_allowed", "Use a domain name, not an IP address")
    try:
        host = host.encode("idna").decode("ascii")     # unicode domains -> punycode
    except UnicodeError:
        raise _err("url_invalid_host", "Domain name is not valid")
    if len(host) > 253:
        raise _err("url_invalid_host", "Domain name is too long")
    if host == "localhost" or host.endswith(BLOCKED_SUFFIXES):
        raise _err("url_host_not_allowed", "Internal hostnames are not allowed")
    if "." not in host or not TLD_RE.match(host.rsplit(".", 1)[-1]):
        raise _err("url_invalid_host", "Enter a valid domain, like example.com")

    netloc = host if (not port or port == DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))   # fragment dropped


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    max_pages: int = Field(default=MAX_PAGES_LIMIT, ge=1, le=MAX_PAGES_LIMIT)

    @field_validator("url", mode="before")
    @classmethod
    def clean_url(cls, v):
        if not isinstance(v, str):
            raise _err("url_invalid", "URL must be a string")
        return normalize_url(v)
    
