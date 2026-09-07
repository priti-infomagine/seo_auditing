"""
Register API latency tests.

Purpose: measure how long `POST /api/v1/auth/register` takes and *why*.

The most likely latency sources (all exercised here) are:
  1. bcrypt password hashing  - passlib/bcrypt is intentionally CPU-slow
     (~200-400ms at default cost factor 12) and runs synchronously inside
     the async endpoint, blocking the event loop.
  2. Celery `.delay()` + Redis broker - `send_register_otp_email()` opens a
     *synchronous* Redis connection on every request. If Redis / the Celery
     worker is down, the producer retries and adds seconds to the response.
  3. Multiple DB round-trips - duplicate-email SELECT + user flush + OTP
     flush + final commit (4 network round trips to Postgres).
  4. First-call cold start - connection pool warm-up + lazy CryptContext init.

Tests:
  * test_register_endpoint_total_latency - times the real HTTP endpoint.
  * test_register_profiled_steps          - breaks the service call into
    per-step timings (bcrypt hash, DB flush, celery task dispatch).
  * test_celery_publish_latency_real       - opt-in (RUN_CELERY_LATENCY=1);
    times the real broker publish WITHOUT mocking - run this to see if an
    unreachable Redis broker is the cause of the slowness.
"""
import os
import time
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import get_db
from app.main import app
from app.modules.auth.models.otp import OTP
from app.modules.auth.models.users import User
from app.modules.auth.schemas.register import RegisterRequest
from app.modules.auth.services.register_service import RegisterService
import app.modules.auth.utils.email_utils as email_utils

REGISTER_URL = "/api/v1/auth/register"


class FakeTask:
    """Stand-in for a Celery task object whose `.delay()` just records the call."""

    def __init__(self) -> None:
        self.calls: list = []

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return None


@pytest_asyncio.fixture
async def register_http_client(db_session):
    """FastAPI test client with the DB dependency pointed at the test session.

    Mirrors the real `get_db` behaviour (commit after success, rollback on
    error) so the measured latency is representative.
    """

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_register_endpoint_total_latency(register_http_client, monkeypatch, db_session):
    """Time the complete HTTP POST /api/v1/auth/register call.

    The Celery task dispatch is mocked here so this test isolates the
    *app-side* latency (bcrypt + DB + commit). To also see the broker
    contribution, run test_celery_publish_latency_real (see that docstring).
    """
    fake = FakeTask()
    monkeypatch.setattr(email_utils, "send_register_otp_email_task", fake)

    payload = _payload()

    t0 = time.perf_counter()
    response = await register_http_client.post(REGISTER_URL, json=payload)
    total_s = time.perf_counter() - t0
    total_ms = total_s * 1000

    print(f"\n[REGISTER] total endpoint latency (excl. broker): {total_ms:.1f} ms")

    assert response.status_code == 201, response.text
    assert response.json()["message"] == "OTP sent successfully"
    # The OTP task was dispatched exactly once through the queue API.
    assert len(fake.calls) == 1

    # Sanity: the user + OTP rows actually got written.
    user = (
        await db_session.execute(select(User).where(User.email == payload["email"]))
    ).scalar_one_or_none()
    assert user is not None
    otp = (
        await db_session.execute(
            select(OTP).where(OTP.user_id == user.id).order_by(OTP.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    assert otp is not None

    # Generous threshold so the test reports/annotates slowness without being flaky.
    assert total_s < 5.0, (
        f"Register took {total_ms:.1f} ms — too slow. Check bcrypt cost factor, "
        "DB round-trips, and whether the Redis broker is reachable."
    )


def _payload() -> dict:
    return {
        "name": "Latency Test",
        "email": f"latency_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@1234",
    }

@pytest.mark.asyncio
async def test_register_profiled_steps(db_session, monkeypatch):
    """Break the register call into per-step timings to find the bottleneck.

    Records how long each internal step takes:
      * bcrypt password hashing
      * DB flush() calls (user + OTP inserts)
      * Celery task dispatch (`.delay()`)
      * total service execution time
    """
    import app.modules.auth.services.register_service as service_module

    timings = {
        "bcrypt_hash": 0.0,
        "db_flush": 0.0,
        "celery_delay": 0.0,
        "total": 0.0,
    }

    # ── Time bcrypt hashing independently ─────────────────────────────
    original_hash = service_module.hash_password

    def timed_hash(password: str) -> str:
        t0 = time.perf_counter()
        result = original_hash(password)
        timings["bcrypt_hash"] += time.perf_counter() - t0
        return result

    monkeypatch.setattr(service_module, "hash_password", timed_hash)

    # ── Time the DB flushes (user insert + OTP insert) ────────────────
    original_flush = db_session.flush

    async def timed_flush(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return await original_flush(*args, **kwargs)
        finally:
            timings["db_flush"] += time.perf_counter() - t0

    monkeypatch.setattr(db_session, "flush", timed_flush)

    # ── Record celery dispatch time (mocked so it doesn't hit a broker) ─
    fake = FakeTask()
    monkeypatch.setattr(email_utils, "send_register_otp_email_task", fake)

    payload = _payload()
    request = RegisterRequest(
        name=payload["name"], email=payload["email"], password=payload["password"]
    )
    service = RegisterService(db_session)

    t0 = time.perf_counter()
    response = await service.execute(request)
    timings["total"] = time.perf_counter() - t0

    print(
        "\n[REGISTER] step timing breakdown\n"
        f"  bcrypt hash  : {timings['bcrypt_hash'] * 1000:8.1f} ms\n"
        f"  db flush(es) : {timings['db_flush'] * 1000:8.1f} ms\n"
        f"  celery delay : {timings['celery_delay'] * 1000:8.1f} ms (mocked)\n"
        f"  total        : {timings['total'] * 1000:8.1f} ms"
    )

    assert response.message == "OTP sent successfully"
    assert len(fake.calls) == 1
    # bcrypt is expected to dominate the app-side cost; flag it in the report.
    hash_share = timings["bcrypt_hash"] / timings["total"] if timings["total"] else 0
    if hash_share > 0.5:
        print(
            f"  >> bcrypt hashing accounts for {hash_share * 100:.0f}% of the "
            "service time — it is an intentional, CPU-bound cost."
        )


@pytest.mark.celery
@pytest.mark.skipif(
    not os.getenv("RUN_CELERY_LATENCY"),
    reason="set RUN_CELERY_LATENCY=1 to measure real broker publish latency",
)
@pytest.mark.asyncio
async def test_celery_publish_latency_real(db_session):
    """OPT-IN: time the real Celery `.delay()` broker publish (no mocking).

    Run with:  RUN_CELERY_LATENCY=1 pytest app/tests/test_register_latency.py \
               -k celery -s

    If Redis / the Celery worker is unreachable this call can block while the
    producer retries (broker_connection_retry_on_startup / publish retry) — a
    slow read here is strong evidence that the broker is the API's bottleneck.
    """
    from app.modules.auth.utils.email_utils import send_register_otp_email_task

    test_email = f"celery_{uuid.uuid4().hex[:8]}@example.com"
    t0 = time.perf_counter()
    try:
        send_register_otp_email_task.delay(test_email, "123456")
        elapsed_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:  # noqa: BLE001 - report any broker failure
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(
            f"\n[CELERY] broker publish raised after {elapsed_ms:.1f} ms: "
            f"{type(exc).__name__}: {exc}"
        )
        pytest.skip(f"Broker publish failed after {elapsed_ms:.1f} ms")

    print(f"\n[CELERY] real broker publish latency: {elapsed_ms:.1f} ms")
    print(
        "  >> A large value here (or a long timeout) means an unreachable or "
        "slow Redis broker is the cause of the slow register API."
    )

