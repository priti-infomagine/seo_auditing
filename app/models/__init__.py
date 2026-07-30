"""
Models package.

Import all SQLAlchemy models here so Alembic can discover them:

    from app.models import *  # noqa: F401, F403
"""

from app.models.auth_models.users import User  # noqa: F401
from app.models.auth_models.otp import OTP  # noqa: F401
from app.models.auth_models.refresh_token import RefreshToken  # noqa: F401

__all__ = ["User", "OTP", "RefreshToken"]
