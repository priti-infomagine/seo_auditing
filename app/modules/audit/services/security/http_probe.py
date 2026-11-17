"""HTTP→HTTPS redirect chain probe."""
import httpx
from .signals import HTTPRedirectSignal


async def probe_http_redirect(http_url: str) -> HTTPRedirectSignal:
    signal = HTTPRedirectSignal(http_url=http_url, final_url=http_url)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(http_url)
            signal.final_url = str(resp.url)
            signal.redirect_chain = [
                {"url": str(r.url), "status": r.status_code} for r in resp.history
            ] + [{"url": str(resp.url), "status": resp.status_code}]
            if signal.final_url.startswith("https://"):
                signal.is_permanent_redirect = any(
                    h.status_code in (301, 308) for h in resp.history
                )
            else:
                signal.http_loads_directly = True
    except httpx.SSLError:
        signal.certificate_error = True
        signal.error = "Certificate error on HTTPS"
    except Exception as e:
        signal.error = str(e)
    return signal