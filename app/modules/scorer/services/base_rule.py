"""
Base rule class for SEO scoring rules.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.modules.scorer.models.rule_result import RuleResult, Severity


class BaseRule(ABC):
    """
    Abstract base class for SEO scoring rules.
    
    Each rule:
    - Receives parsed data from the parser service
    - Evaluates one or more conditions
    - Returns RuleResult(s) with score impact
    """
    
    rule_id: str = ""
    name: str = ""
    category: str = ""
    description: str = ""
    weight: float = 1.0
    tags: List[str] = []
    
    def __init__(self):
        if not self.rule_id:
            raise ValueError(f"Rule {self.__class__.__name__} must define rule_id")
        if not self.name:
            raise ValueError(f"Rule {self.__class__.__name__} must define name")
    
    @abstractmethod
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        """
        Evaluate the rule against parsed data.
        
        Args:
            data: Parsed SEO data from parser service
            
        Returns:
            List of RuleResult objects (usually one, but can be multiple)
        """
        pass
    
    def _create_result(
        self,
        passed: bool,
        message: str,
        severity: Severity = Severity.INFO,
        score_impact: float = 0.0,
        recommendation: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> RuleResult:
        """Helper to create a RuleResult."""
        return RuleResult(
            rule_id=self.rule_id,
            name=self.name,
            category=self.category,
            severity=severity,
            passed=passed,
            score_impact=score_impact,
            message=message,
            recommendation=recommendation,
            data=data,
            tags=self.tags,
        )