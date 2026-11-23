from pydantic import BaseModel, Field
from typing import List, Optional


class EEATSignal(BaseModel):
    """Individual trust signal with confidence and evidence."""
    found: bool = False
    confidence: float = 0.0  # 0.0-1.0
    evidence: str = ""       # What was found (URL, text snippet, selector match)
    location: str = ""       # Selector or element description


class EEATData(BaseModel):
    """Complete E-E-A-T signal extraction result."""
    # Policy & Legal
    privacy_policy: EEATSignal = Field(default_factory=EEATSignal)
    terms_of_service: EEATSignal = Field(default_factory=EEATSignal)
    editorial_policy: EEATSignal = Field(default_factory=EEATSignal)
    
    # Author & Expertise
    author_byline: EEATSignal = Field(default_factory=EEATSignal)
    author_expertise: EEATSignal = Field(default_factory=EEATSignal)
    
    # Content Transparency
    content_dates: EEATSignal = Field(default_factory=EEATSignal)  # published/modified
    
    # Business Trust
    physical_address: EEATSignal = Field(default_factory=EEATSignal)
    about_page: EEATSignal = Field(default_factory=EEATSignal)
    contact_page: EEATSignal = Field(default_factory=EEATSignal)
    
    # Trust Indicators
    trust_signals: EEATSignal = Field(default_factory=EEATSignal)  # certifications, badges, reviews
    disclaimers: EEATSignal = Field(default_factory=EEATSignal)
    affiliate_disclosure: EEATSignal = Field(default_factory=EEATSignal)
    
    # Content Quality
    external_citations: EEATSignal = Field(default_factory=EEATSignal)
    
    # Context Classification
    ymyl_topics: EEATSignal = Field(default_factory=EEATSignal)  # YMYL detection
    
    # Computed helpers
    @property
    def signal_count(self) -> int:
        return sum(1 for s in self.model_dump().values() if isinstance(s, EEATSignal) and s.found)
    
    @property
    def avg_confidence(self) -> float:
        signals = [s for s in self.model_dump().values() if isinstance(s, EEATSignal) and s.found]
        return sum(s.confidence for s in signals) / len(signals) if signals else 0.0