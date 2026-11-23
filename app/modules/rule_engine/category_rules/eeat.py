"""
E-E-A-T Rules — Category 10
Observable trust indicators for credibility evaluation.
"""
from typing import Any, Dict, List
from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class EEATBaseRule(BaseRule):
    """Base class for EEAT rules — evaluates pre-computed EEATSignal."""
    
    def _get_signal(self, data: Dict[str, Any], signal_name: str):
        """Extract EEATSignal from rule data dict."""
        eeat_data = data.get("eeat", {})
        if not eeat_data:
            return None
        # Handle both object and dict (from JSONB serialization)
        signal = eeat_data.get(signal_name)
        if signal and hasattr(signal, 'found'):
            return signal
        if isinstance(signal, dict):
            # Reconstruct signal-like object
            class SignalProxy:
                def __init__(self, d):
                    self.found = d.get("found", False)
                    self.confidence = d.get("confidence", 0.0)
                    self.evidence = d.get("evidence", "")
                    self.location = d.get("location", "")
            return SignalProxy(signal)
        return None

    def _evaluate_signal(
        self, 
        signal, 
        data: Dict[str, Any],
        passed_msg: str, 
        failed_msg: str,
        base_impact: float = 1.0,
        ymyl_multiplier: float = 1.5,
        data_key: str = None
    ) -> List[RuleResult]:
        """Standard evaluation with YMYL-aware scoring."""
        if not signal:
            return [self._create_result(
                passed=False,
                message="EEAT data not available",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Ensure EEAT extractor runs in parser pipeline",
            )]
        
        # Check YMYL context for adjusted severity
        ymyl_signal = self._get_signal(data, "ymyl_topics")
        is_ymyl = ymyl_signal and ymyl_signal.found
        
        if signal.found:
            impact = base_impact
            if is_ymyl:
                impact *= ymyl_multiplier  # Bonus for YMYL pages having the signal
            
            return [self._create_result(
                passed=True,
                message=passed_msg.format(evidence=signal.evidence[:200]),
                severity=Severity.PASSED,
                score_impact=impact,
                data={data_key or "signal": signal.evidence, "confidence": signal.confidence, "ymyl": is_ymyl},
            )]
        else:
            impact = -base_impact
            severity = Severity.WARNING
            if is_ymyl:
                impact *= ymyl_multiplier  # Penalty for YMYL pages missing signal
                severity = Severity.WARNING  # Could be CRITICAL for specific signals
            
            return [self._create_result(
                passed=False,
                message=failed_msg,
                severity=severity,
                score_impact=impact,
                recommendation=self._get_recommendation(signal, is_ymyl),
                data={"ymyl": is_ymyl, "missing_signal": True},
            )]

    def _get_recommendation(self, signal, is_ymyl: bool) -> str:
        base = "Add this trust signal to improve credibility"
        if is_ymyl:
            return f"{base} (especially important for YMYL content)"
        return base


# === 14 Individual Rules ===

class PrivacyPolicyRule(EEATBaseRule):
    """eeat_001 — Privacy policy link present."""
    rule_id = "eeat_001"
    name = "Privacy Policy"
    category = "eeat"
    description = "Page or site provides accessible privacy policy link"
    weight = 1.2
    tags = ["trust", "compliance", "privacy", "legal"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "privacy_policy")
        return self._evaluate_signal(
            signal, data,
            "Privacy policy found: {evidence}",
            "No privacy policy link detected",
            base_impact=2.0,
            data_key="privacy_policy_url",
        )


class TermsOfServiceRule(EEATBaseRule):
    """eeat_002 — Terms of service link present."""
    rule_id = "eeat_002"
    name = "Terms of Service"
    category = "eeat"
    description = "Site provides terms of service / terms of use link"
    weight = 1.1
    tags = ["trust", "compliance", "legal"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "terms_of_service")
        return self._evaluate_signal(
            signal, data,
            "Terms of service found: {evidence}",
            "No terms of service link detected",
            base_impact=1.5,
            data_key="terms_url",
        )


class AuthorBylineRule(EEATBaseRule):
    """eeat_003 — Author byline/attribution present."""
    rule_id = "eeat_003"
    name = "Author Byline"
    category = "eeat"
    description = "Content includes visible author attribution"
    weight = 1.5
    tags = ["author", "transparency", "e-e-a-t"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "author_byline")
        return self._evaluate_signal(
            signal, data,
            "Author byline found: {evidence}",
            "No author byline detected",
            base_impact=3.0,
            ymyl_multiplier=2.0,
            data_key="author_name",
        )


class AuthorExpertiseRule(EEATBaseRule):
    """eeat_004 — Author expertise/credentials visible."""
    rule_id = "eeat_004"
    name = "Author Expertise Signals"
    category = "eeat"
    description = "Observable author credentials, biography, or expertise information"
    weight = 1.4
    tags = ["author", "expertise", "e-e-a-t"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "author_expertise")
        return self._evaluate_signal(
            signal, data,
            "Author expertise signals found: {evidence}",
            "No author expertise/credentials detected",
            base_impact=2.0,
            ymyl_multiplier=2.0,
            data_key="expertise_evidence",
        )


class ContentDatesRule(EEATBaseRule):
    """eeat_005 — Publication/modification dates present."""
    rule_id = "eeat_005"
    name = "Content Dates"
    category = "eeat"
    description = "Visible publication or updated dates where applicable"
    weight = 1.0
    tags = ["freshness", "transparency", "content-quality"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "content_dates")
        return self._evaluate_signal(
            signal, data,
            "Content dates found: {evidence}",
            "No publication/modification dates detected",
            base_impact=1.0,
            ymyl_multiplier=1.5,
            data_key="dates_found",
        )


class PhysicalAddressRule(EEATBaseRule):
    """eeat_006 — Physical business address displayed."""
    rule_id = "eeat_006"
    name = "Physical Address"
    category = "eeat"
    description = "Business physical address displayed where relevant"
    weight = 1.1
    tags = ["trust", "local-business", "contact"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "physical_address")
        return self._evaluate_signal(
            signal, data,
            "Physical address found: {evidence}",
            "No physical address detected",
            base_impact=1.5,
            ymyl_multiplier=1.5,
            data_key="address",
        )


class EditorialPolicyRule(EEATBaseRule):
    """eeat_007 — Editorial policy/standards link present."""
    rule_id = "eeat_007"
    name = "Editorial Policy"
    category = "eeat"
    description = "Site provides editorial policy or content standards information"
    weight = 1.0
    tags = ["transparency", "editorial", "publishing"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "editorial_policy")
        return self._evaluate_signal(
            signal, data,
            "Editorial policy found: {evidence}",
            "No editorial policy link detected",
            base_impact=1.0,
            data_key="editorial_url",
        )


class TrustSignalsRule(EEATBaseRule):
    """eeat_008 — Visible trust indicators (badges, certifications, reviews)."""
    rule_id = "eeat_008"
    name = "Trust Signals"
    category = "eeat"
    description = "Observable trust indicators: certifications, testimonials, reviews, badges"
    weight = 1.3
    tags = ["trust", "social-proof", "credibility"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "trust_signals")
        return self._evaluate_signal(
            signal, data,
            "Trust signals found: {evidence}",
            "No trust signals (badges, reviews, certifications) detected",
            base_impact=2.0,
            ymyl_multiplier=1.5,
            data_key="trust_evidence",
        )


class DisclaimersRule(EEATBaseRule):
    """eeat_009 — Relevant disclaimers present."""
    rule_id = "eeat_009"
    name = "Disclaimers"
    category = "eeat"
    description = "Relevant disclaimers present for content that may require them"
    weight = 1.2
    tags = ["compliance", "transparency", "legal"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "disclaimers")
        ymyl_signal = self._get_signal(data, "ymyl_topics")
        is_ymyl = ymyl_signal and ymyl_signal.found
        
        if signal.found:
            return [self._create_result(
                passed=True,
                message=f"Disclaimer found: {signal.evidence[:200]}",
                severity=Severity.PASSED,
                score_impact=1.5,
                data={"disclaimer": signal.evidence, "ymyl": is_ymyl},
            )]
        else:
            # Only warn for YMYL or pages that likely need disclaimers
            if is_ymyl:
                return [self._create_result(
                    passed=False,
                    message="No disclaimer detected on YMYL content",
                    severity=Severity.WARNING,
                    score_impact=-3.0,
                    recommendation="Add appropriate disclaimer (medical, financial, legal, etc.)",
                    data={"ymyl": True},
                )]
            return [self._create_result(
                passed=True,
                message="No disclaimer detected (not required for non-YMYL content)",
                severity=Severity.INFO,
                score_impact=0,
                data={"ymyl": False},
            )]


class AboutPageRule(EEATBaseRule):
    """eeat_010 — About page link present."""
    rule_id = "eeat_010"
    name = "About Page Link"
    category = "eeat"
    description = "Site provides About page or link to organizational information"
    weight = 1.0
    tags = ["transparency", "organization", "trust"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "about_page")
        return self._evaluate_signal(
            signal, data,
            "About page found: {evidence}",
            "No About page link detected",
            base_impact=1.0,
            data_key="about_url",
        )


class ContactPageRule(EEATBaseRule):
    """eeat_011 — Contact page link present."""
    rule_id = "eeat_011"
    name = "Contact Page Link"
    category = "eeat"
    description = "Site provides contact page or link to contact information"
    weight = 1.1
    tags = ["trust", "contact", "accessibility"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "contact_page")
        return self._evaluate_signal(
            signal, data,
            "Contact page found: {evidence}",
            "No contact page link detected",
            base_impact=1.5,
            ymyl_multiplier=1.5,
            data_key="contact_url",
        )


class ExternalCitationsRule(EEATBaseRule):
    """eeat_012 — External references/citations present."""
    rule_id = "eeat_012"
    name = "External Citations"
    category = "eeat"
    description = "External references or citations supporting content claims"
    weight = 1.2
    tags = ["credibility", "evidence", "sources"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "external_citations")
        return self._evaluate_signal(
            signal, data,
            "External citations found: {evidence}",
            "No external citations/references detected",
            base_impact=1.5,
            ymyl_multiplier=2.0,
            data_key="citations",
        )


class AffiliateDisclosureRule(EEATBaseRule):
    """eeat_013 — Affiliate disclosure present when applicable."""
    rule_id = "eeat_013"
    name = "Affiliate Disclosure"
    category = "eeat"
    description = "Affiliate relationship disclosures present when affiliate links detected"
    weight = 1.3
    tags = ["transparency", "compliance", "affiliate", "ftc"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "affiliate_disclosure")
        
        # Also check if affiliate links exist on page
        links = data.get("links", {})
        external_links = links.get("external_links", [])
        has_affiliate_links = any(
            "affiliate" in (l.get("href", "") + l.get("anchor_text", "")).lower()
            for l in external_links
        )
        
        if signal.found:
            return [self._create_result(
                passed=True,
                message=f"Affiliate disclosure found: {signal.evidence[:200]}",
                severity=Severity.PASSED,
                score_impact=2.0,
                data={"disclosure": signal.evidence, "has_affiliate_links": has_affiliate_links},
            )]
        elif has_affiliate_links:
            return [self._create_result(
                passed=False,
                message="Affiliate links detected but no disclosure found",
                severity=Severity.WARNING,
                score_impact=-4.0,
                recommendation="Add clear affiliate disclosure per FTC guidelines",
                data={"has_affiliate_links": True},
            )]
        else:
            return [self._create_result(
                passed=True,
                message="No affiliate links detected; disclosure not required",
                severity=Severity.INFO,
                score_impact=0,
                data={"has_affiliate_links": False},
            )]


class YMYLDetectionRule(EEATBaseRule):
    """eeat_014 — YMYL topic detection for context-sensitive evaluation."""
    rule_id = "eeat_014"
    name = "YMYL Detection"
    category = "eeat"
    description = "Identifies financial, health, safety, or other consequential topics"
    weight = 1.0
    tags = ["context", "ymyl", "classification"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        signal = self._get_signal(data, "ymyl_topics")
        
        if signal.found:
            return [self._create_result(
                passed=True,
                message=f"YMYL topics detected: {signal.evidence}",
                severity=Severity.INFO,
                score_impact=0,  # Informational only — affects other rules
                data={"ymyl": True, "topics": signal.evidence},
            )]
        else:
            return [self._create_result(
                passed=True,
                message="No YMYL topics detected",
                severity=Severity.INFO,
                score_impact=0,
                data={"ymyl": False},
            )]