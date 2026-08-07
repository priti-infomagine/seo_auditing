from app.shared.services.email_service import send_email

async def send_register_otp_email(to_email: str, otp: str):
    subject = "Your OTP for Registration"
    content = f"registering for SEO Audit Tool. Your OTP is: {otp}. It will expire in 10 minutes."
    await send_email(to_email=to_email, subject=subject, content=content)

async def send_welcome_email(to_email: str):
    subject = "Welcome to SEO Audit Tool!"
    content = "Thank you for registering with SEO Audit Tool. We're excited to have you on board!"
    await send_email(to_email=to_email, subject=subject, content=content) 

async def send_password_reset_otp_email(to_email: str, otp: str):
    subject = "Your OTP for Password Reset"
    content = f"You requested a password reset. Your OTP is: {otp}. It will expire in 10 minutes."
    await send_email(to_email=to_email, subject=subject, content=content)