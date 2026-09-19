from uuid import UUID

from pydantic import BaseModel, Field
from typing import Optional, List




class LighthouseCheckRequest(BaseModel):
    url: str = Field(
        ..., 
        description="The URL to check"
    )
    device: str = Field(
        ..., 
        description="The device type for the check (e.g., 'mobile' or 'desktop')"
    )
    category: Optional[List[str]] = Field(
        None, # performance, seo, best-practices, accessibility
        description="The Lighthouse categories to include in the check [performance, seo, best-practices, accessibility]"
    )
    version: Optional[str] = Field(
        None,
    )
    max_pages: Optional[int] = Field(
        ...,
    )
    
    
class LighthouseCheckResponse(BaseModel):
    id: UUID = Field(
        ...,
        description="The unique identifier for the Lighthouse check result"
    )
    url: str = Field(
        ...,
        description="The URL that was checked"
    )
    device: str = Field(
        ...,
        description="The device type for the check (e.g., 'mobile' or 'desktop')"
    )
    status: str = Field(
        ...,
        description="The status of the Lighthouse check (e.g., 'success', 'failed', 'skipped')"
    )
    reason: Optional[str] = Field(
        None,
        description="The reason for the status if applicable (e.g., skip reason or error message)"
    )
    performance_score: Optional[int] = Field(
        None,
        description="The performance score from the Lighthouse check (0-100)"
    )
    seo_score: Optional[int] = Field(
        None,
        description="The SEO score from the Lighthouse check (0-100)"
    )
    fcp_ms: Optional[int] = Field(
        None,
        description="First Contentful Paint in milliseconds"
    )
    lcp_ms: Optional[int] = Field(
        None,
        description="Largest Contentful Paint in milliseconds"
    )
    tbt_ms: Optional[int] = Field(
        None,
        description="Total Blocking Time in milliseconds"
    )
    cls: Optional[float] = Field(
        None,
        description="Cumulative Layout Shift score"
    )
    
    
    