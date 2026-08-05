"""
Quick test for password reset schema validations.
"""
from pydantic import ValidationError
from app.schemas.auth_schemas.forgot_password import (
    ForgotPasswordRequest,
    VerifyResetOTPRequest,
    ResetPasswordRequest,
)


def test_forgot_password_request():
    req = ForgotPasswordRequest(email="test@example.com")
    assert req.email == "test@example.com"
    print("ForgotPasswordRequest: OK")


def test_verify_reset_otp_request():
    req = VerifyResetOTPRequest(email="test@example.com", otp="123456")
    assert req.email == "test@example.com"
    assert req.otp == "123456"
    print("VerifyResetOTPRequest: OK")


def test_reset_password_request():
    req = ResetPasswordRequest(
        email="test@example.com",
        new_password="NewPass@123",
        confirm_password="NewPass@123",
    )
    assert req.email == "test@example.com"
    print("ResetPasswordRequest: OK")


def test_weak_password():
    try:
        ResetPasswordRequest(
            email="test@example.com",
            new_password="weak",
            confirm_password="weak",
        )
        assert False, "Should have raised ValidationError"
    except ValidationError as e:
        assert len(e.errors()) > 0
        print(f"Weak password validation: OK - {e.errors()[0]['msg']}")


def test_password_mismatch():
    try:
        ResetPasswordRequest(
            email="test@example.com",
            new_password="NewPass@123",
            confirm_password="Mismatch@123",
        )
        assert False, "Should have raised ValidationError"
    except ValidationError as e:
        assert len(e.errors()) > 0
        print(f"Password mismatch validation: OK - {e.errors()[0]['msg']}")


def test_invalid_otp_format():
    try:
        VerifyResetOTPRequest(email="test@example.com", otp="abc")
        assert False, "Should have raised ValidationError"
    except ValidationError as e:
        assert len(e.errors()) > 0
        print(f"Invalid OTP format validation: OK - {e.errors()[0]['msg']}")


if __name__ == "__main__":
    test_forgot_password_request()
    test_verify_reset_otp_request()
    test_reset_password_request()
    test_weak_password()
    test_password_mismatch()
    test_invalid_otp_format()
    print("\nAll schema validation tests passed!")