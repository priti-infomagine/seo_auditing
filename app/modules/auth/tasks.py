from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.modules.auth.models.otp import OTP
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.shared.tasks.celery_app import celery_app
from app.shared.services.email_service import send_email_sync


@celery_app.task(
    name="auth.send_register_otp_email",
    queue="email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def send_register_otp_email_task(to_email: str, otp: str) -> None:
    subject = "Your OTP for Registration"
    content = f"registering for SEO Audit Tool. Your OTP is: {otp}. It will expire in 10 minutes."
    send_email_sync(to_email=to_email, subject=subject, content=content)


@celery_app.task(
    name="auth.send_welcome_email",
    queue="email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def send_welcome_email_task(to_email: str) -> None:
    subject = "Welcome to SEO Audit Tool!"
    content = "Thank you for registering with SEO Audit Tool. We're excited to have you on board!"
    send_email_sync(to_email=to_email, subject=subject, content=content)


@celery_app.task(
    name="auth.send_password_reset_otp_email",
    queue="email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def send_password_reset_otp_email_task(to_email: str, otp: str) -> None:
    subject = "Your OTP for Password Reset"
    content = f"You requested a password reset. Your OTP is: {otp}. It will expire in 10 minutes."
    send_email_sync(to_email=to_email, subject=subject, content=content)


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


@celery_app.task(name="auth.cleanup_expired_otps")
def cleanup_expired_otps() -> int:
    now = datetime.now(timezone.utc)

    async def _cleanup():
        async with async_session_factory() as session:
            result = await session.execute(
                delete(OTP).where(OTP.expires_at < now)
            )
            await session.commit()
            return result.rowcount

    return _run_async(_cleanup())


@celery_app.task(name="auth.cleanup_expired_blacklisted_tokens")
def cleanup_expired_blacklisted_tokens() -> int:
    now = datetime.now(timezone.utc)

    async def _cleanup():
        async with async_session_factory() as session:
            result = await session.execute(
                delete(TokenBlacklist).where(TokenBlacklist.expires_at < now)
            )
            await session.commit()
            return result.rowcount

    return _run_async(_cleanup())


@celery_app.task(name="auth.cleanup_expired_refresh_tokens")
def cleanup_expired_refresh_tokens() -> int:
    now = datetime.now(timezone.utc)

    async def _cleanup():
        async with async_session_factory() as session:
            result = await session.execute(
                delete(RefreshToken).where(
                    RefreshToken.expires_at < now,
                )
            )
            await session.commit()
            return result.rowcount

    return _run_async(_cleanup())
