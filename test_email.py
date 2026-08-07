from dotenv import load_dotenv
import os

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("SMTP_FROM_EMAIL") or os.getenv("EMAIL_FROM")

print("SMTP_HOST:", SMTP_HOST)
print("SMTP_PORT:", SMTP_PORT)
print("SMTP_USER:", SMTP_USER)
print("EMAIL_FROM:", EMAIL_FROM)

if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM]):
    missing = [v for v in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM/SMTP_FROM_EMAIL"] if not os.getenv(v)]
    raise RuntimeError(f"Missing SMTP env vars: {missing}")

from email.message import EmailMessage
import aiosmtplib

async def send_email(to_email: str):
    print(f"Sending email to: {to_email}")
    msg = EmailMessage()
    msg["Subject"] = "Test Email"
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email

    msg.set_content("Hello! This is a test email from FastAPI.")

    try:
        result = await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        print("SMTP response:", result)
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise

async def test_email():
    print("Testing email sending...")
    await send_email("priti.backend.dev@gmail.com")
    return {"message": "Email sent successfully"}

import asyncio

if __name__ == "__main__":
    asyncio.run(test_email())