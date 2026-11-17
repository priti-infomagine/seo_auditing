"""Fetch and parse security headers from HTTPS response."""
import httpx


async def fetch_security_headers(url: str) -> dict:
    result = {"headers": {}, "hsts": "", "hsts_max_age": None, "hsts_include_subdomains": False, "hsts_preload": False}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, follow_redirects=True)
            result["headers"] = {k.lower(): v for k, v in resp.headers.items()}
            hsts = resp.headers.get("strict-transport-security", "")
            result["hsts"] = hsts
            if hsts:
                for part in hsts.split(";"):
                    part = part.strip().lower()
                    if part.startswith("max-age="):
                        try:
                            result["hsts_max_age"] = int(part.split("=")[1])
                        except (ValueError, IndexError):
                            pass
                    elif part == "includesubdomains":
                        result["hsts_include_subdomains"] = True
                    elif part == "preload":
                        result["hsts_preload"] = True
    except Exception:
        pass
    return result