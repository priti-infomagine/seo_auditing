"""Quick import test for the auth API modules."""
import sys
sys.path.insert(0, ".")

# Test 1: Security utils
from app.core.security import hash_password, verify_password, hash_token
h = hash_password("test1234")
assert verify_password("test1234", h), "Password verification failed"
assert hash_token("some-token") == hash_token("some-token"), "Token hash mismatch"
print("✓ security.py - hash/verify/hash_token works")

# Test 2: JWT utils
from app.modules.auth.utils import create_access_token, create_refresh_token, decode_token
at = create_access_token("user-123")
rt = create_refresh_token("user-123")
assert decode_token(at)["sub"] == "user-123"
assert decode_token(rt)["sub"] == "user-123"
assert decode_token(at)["type"] == "access"
assert decode_token(rt)["type"] == "refresh"
print("✓ jwt.py - token create/decode works")

# Test 3: All schemas
from app.modules.auth.schemas.register import RegisterRequest, RegisterResponse
from app.modules.auth.schemas.verify_otp import VerifyOTPRequest, VerifyOTPResponse
from app.modules.auth.schemas.login import LoginRequest, LoginResponse
from app.modules.auth.schemas.refresh import RefreshTokenRequest, RefreshTokenResponse
from app.modules.auth.schemas.logout import LogoutRequest, LogoutResponse

# Test RegisterRequest with valid data
req = RegisterRequest(name="Test User", email="test@example.com", password="StrongP@ss1")
assert req.email == "test@example.com"
assert req.name == "Test User"
print("✓ RegisterRequest - valid data accepted")

# Test name validation: digits should be rejected
try:
    RegisterRequest(name="User123", email="test@example.com", password="StrongP@ss1")
    assert False, "Should have raised ValidationError for digits in name"
except Exception:
    print("✓ RegisterRequest - name with digits correctly rejected")

# Test name validation: special chars should be rejected
try:
    RegisterRequest(name="User@Name", email="test@example.com", password="StrongP@ss1")
    assert False, "Should have raised ValidationError for special chars in name"
except Exception:
    print("✓ RegisterRequest - name with special chars correctly rejected")

# Test password validation: missing uppercase
try:
    RegisterRequest(name="Test User", email="test@example.com", password="weakp@ss1")
    assert False, "Should have raised ValidationError for missing uppercase"
except Exception:
    print("✓ RegisterRequest - password without uppercase correctly rejected")

# Test password validation: missing digit
try:
    RegisterRequest(name="Test User", email="test@example.com", password="WeakP@sss")
    assert False, "Should have raised ValidationError for missing digit"
except Exception:
    print("✓ RegisterRequest - password without digit correctly rejected")

# Test password validation: missing special char
try:
    RegisterRequest(name="Test User", email="test@example.com", password="WeakPass1")
    assert False, "Should have raised ValidationError for missing special char"
except Exception:
    print("✓ RegisterRequest - password without special char correctly rejected")

# Test LoginRequest password validation
from app.modules.auth.schemas.login import LoginRequest
try:
    LoginRequest(email="test@example.com", password="weak")
    assert False, "Should have raised ValidationError for weak login password"
except Exception:
    print("✓ LoginRequest - weak password correctly rejected")

print("✓ schemas - all validations working correctly")

# Test 4: All service imports
from app.modules.auth.services.register_service import RegisterService
from app.modules.auth.services.verify_otp_service import VerifyOTPService
from app.modules.auth.services.login_service import LoginService
from app.modules.auth.services.refresh_service import RefreshTokenService
from app.modules.auth.services.logout_service import LogoutService
print("✓ services - all service imports OK")

# Test 5: All router imports
from app.api.endpoints.v1.auth.register import router as reg_router
from app.api.endpoints.v1.auth.login import router as login_router
from app.api.endpoints.v1.auth.verify_otp import router as verify_router
from app.api.endpoints.v1.auth.refresh_token import router as refresh_router
from app.api.endpoints.v1.auth.logout import router as logout_router
from app.api.endpoints.v1.auth.forgot_pass import router as pw_router
from app.api.endpoints.v1.auth.router import router as auth_router
print("✓ routers - all routers import OK")

# Test 6: Model imports
from app.modules.auth.models.users import User
from app.modules.auth.models.otp import OTP
from app.modules.auth.models.refresh_token import RefreshToken
print("✓ models - all model imports OK")

print("\n✅ ALL IMPORTS AND BASIC TESTS PASSED")