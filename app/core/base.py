"""
Re-export the declarative Base so models can do:

    from app.core.base import Base
"""
from app.core.database import Base

__all__ = ["Base"]