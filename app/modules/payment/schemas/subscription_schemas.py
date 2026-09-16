from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SubscriptionCreate(BaseModel):
    plan_id: UUID
    user_id: UUID
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    user_id: UUID
    status: str
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None
    updated_at: datetime