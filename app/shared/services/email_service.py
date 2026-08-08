import os
from email.message import EmailMessage
import smtplib

from dotenv import load_dotenv

load_dotenv()


def _get_smtp_settings() -> dict:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM_EMAIL") or os.getenv("EMAIL_FROM")
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
    }


def send_email_sync(to_email: str, subject: str, content: str) -> None:
    settings = _get_smtp_settings()
    if not all([settings["host"], settings["username"], settings["password"], settings["sender"]]):
        missing = [
            v
            for v in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM/SMTP_FROM_EMAIL"]
            if not os.getenv(v)
        ]
        raise RuntimeError(f"Missing SMTP env vars: {missing}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["sender"]
    msg["To"] = to_email
    msg.set_content(content)

    try:
        with smtplib.SMTP(settings["host"], settings["port"]) as server:
            server.starttls()
            server.login(settings["username"], settings["password"])
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise


async def send_email(to_email: str, subject: str | None = None, content: str | None = None):
    msg = EmailMessage()
    msg["Subject"] = subject or "Test Email"
    msg["From"] = _get_smtp_settings()["sender"]
    msg["To"] = to_email
    msg.set_content(content or "Hello! This is a test email from FastAPI.")

    try:
        import aiosmtplib

        result = await aiosmtplib.send(
            msg,
            hostname=_get_smtp_settings()["host"],
            port=int(os.getenv("SMTP_PORT", "587")),
            username=_get_smtp_settings()["username"],
            password=_get_smtp_settings()["password"],
            start_tls=True,
        )
        print("SMTP response:", result)
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise
