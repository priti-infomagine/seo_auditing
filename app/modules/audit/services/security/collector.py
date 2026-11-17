"""Collect site signals once per audit and cache in Redis."""
import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from app.core.redis import get_redis
from .signals import SiteSignals, TLSSignal, HTTPRedirectSignal
from .tls_probe import probe_tls
from .http_probe import probe_http_redirect
from .security_headers import fetch_security_headers

SITE_SIGNALS_TTL = 600 # 10 minutes


def _redis_key(audit_id: str) -> str:
    return f"audit:site_signals:{audit_id}"


def _serialize_site_signals(signals: SiteSignals) -> str:
    """Serialize SiteSignals to JSON string."""
    return json.dumps(_asdict_compat(signals), default=str)


def _asdict_compat(obj):
    """Convert dataclass to dict, handling nested dataclasses."""
    if hasattr(obj, '__dataclass_fields__'):
        result = {}
        for field_name in obj.__dataclass_fields__:
            value = getattr(obj, field_name)
            if hasattr(value, '__dataclass_fields__'):
                result[field_name] = _asdict_compat(value)
            elif isinstance(value, list):
                result[field_name] = [_asdict_compat(v) if hasattr(v, '__dataclass_fields__') else v for v in value]
            elif isinstance(value, dict):
                result[field_name] = {k: _asdict_compat(v) for k, v in value.items()}
            elif isinstance(value, datetime):
                result[field_name] = value.isoformat()
            else:
                result[field_name] = value
        return result
    return obj


def _deserialize_site_signals(data: dict) -> SiteSignals:
    """Deserialize dict to SiteSignals."""
    # Handle nested TLSSignal
    if data.get("tls"):
        tls_data = data["tls"]
        if tls_data.get("certificate_expiry") and isinstance(tls_data["certificate_expiry"], str):
            try:
                tls_data["certificate_expiry"] = datetime.fromisoformat(tls_data["certificate_expiry"])
            except ValueError:
                tls_data["certificate_expiry"] = None
        data["tls"] = TLSSignal(**tls_data)
    
    # Handle nested HTTPRedirectSignal
    if data.get("http_redirect"):
        data["http_redirect"] = HTTPRedirectSignal(**data["http_redirect"])
    
    # Handle collected_at
    if data.get("collected_at") and isinstance(data["collected_at"], str):
        try:
            # Just keep as string, it's already ISO format
            pass
        except ValueError:
            pass
    
    return SiteSignals(**data)


async def collect_site_signals(audit_id: str, start_url: str) -> SiteSignals:
    """Collect site-level security signals once per audit."""
    parsed = urlparse(start_url)
    hostname = parsed.hostname
    signals = SiteSignals(base_url=start_url, hostname=hostname)

    tasks = []
    if parsed.scheme == "https":
        tasks.append(probe_tls(hostname))
    tasks.append(probe_http_redirect(f"http://{hostname}/"))
    if parsed.scheme == "https":
        tasks.append(fetch_security_headers(start_url))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, TLSSignal):
            signals.tls = r
        elif isinstance(r, HTTPRedirectSignal):
            signals.http_redirect = r
        elif isinstance(r, dict):
            signals.security_headers = r.get("headers", {})
            signals.hsts_header = r.get("hsts", "")
            signals.hsts_max_age = r.get("hsts_max_age")
            signals.hsts_include_subdomains = r.get("hsts_include_subdomains", False)
            signals.hsts_preload = r.get("hsts_preload", False)

    # Cache in Redis
    redis = await get_redis()
    if redis:
        try:
            await redis.setex(_redis_key(audit_id), SITE_SIGNALS_TTL, _serialize_site_signals(signals))
        except Exception:
            pass

    return signals


async def get_site_signals(audit_id: str) -> Optional[SiteSignals]:
    """Retrieve cached site signals from Redis."""
    redis = await get_redis()
    if not redis:
        return None
    try:
        data = await redis.get(_redis_key(audit_id))
        if not data:
            return None
        return _deserialize_site_signals(json.loads(data))
    except Exception:
        return None