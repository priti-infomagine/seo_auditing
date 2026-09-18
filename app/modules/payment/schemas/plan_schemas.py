"""Plan schemas for API responses."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlanResponse(BaseModel):
    """Plan response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    plan_type: str
    billing_interval: Optional[str] = None
    price: Decimal
    currency: str
    audit_limit: Optional[int] = None
    fair_usage_enabled: bool
    report_type: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PlanListResponse(BaseModel):
    """Plan list response schema."""

    plans: List[PlanResponse]
    total: int
    limit: int
    offset: int