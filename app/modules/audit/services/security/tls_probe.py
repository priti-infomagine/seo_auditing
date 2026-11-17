"""TLS handshake probe - runs in thread pool (blocking)."""
import asyncio
import socket
import ssl
from datetime import datetime
from typing import Optional

from .signals import TLSSignal


async def probe_tls(hostname: str, port: int = 443) -> TLSSignal:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _probe_tls_sync, hostname, port)


def _probe_tls_sync(hostname: str, port: int) -> TLSSignal:
    signal = TLSSignal(hostname=hostname, port=port)
    try:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                signal.tls_version = ssock.version()
                signal.cipher = ssock.cipher()[0] if ssock.cipher() else None
                cert = ssock.getpeercert()
                if cert:
                    signal.certificate_valid = True
                    signal.certificate_issuer = dict(cert.get('issuer', [])).get('commonName', '')
                    not_after = cert.get('notAfter', '')
                    if not_after:
                        signal.certificate_expiry = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                    for ext in cert.get('subjectAltName', []):
                        signal.certificate_san.append(ext[1])
                    signal.chain_trusted = True
        signal.tested_tls10 = _test_legacy_tls(hostname, port, ssl.PROTOCOL_TLSv1)
        signal.tested_tls11 = _test_legacy_tls(hostname, port, ssl.PROTOCOL_TLSv1_1)
    except ssl.SSLCertVerificationError as e:
        signal.error = f"Certificate verification failed: {e}"
    except ssl.SSLError as e:
        signal.error = f"TLS error: {e}"
    except Exception as e:
        signal.error = f"Connection error: {e}"
    return signal


def _test_legacy_tls(hostname: str, port: int, protocol) -> Optional[bool]:
    try:
        context = ssl.SSLContext(protocol)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname):
                return True
    except ssl.SSLError:
        return False
    except Exception:
        return None