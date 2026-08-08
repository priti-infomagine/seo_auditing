from app.modules.auth.tasks import (
    send_register_otp_email_task,
    send_welcome_email_task,
    send_password_reset_otp_email_task,
)


def send_register_otp_email(to_email: str, otp: str):
    send_register_otp_email_task.delay(to_email, otp)


def send_welcome_email(to_email: str):
    send_welcome_email_task.delay(to_email)


def send_password_reset_otp_email(to_email: str, otp: str):
    send_password_reset_otp_email_task.delay(to_email, otp)
