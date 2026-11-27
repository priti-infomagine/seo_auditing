"""Build a versioned, consistent evidence envelope from rule output."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.modules.rule_engine.models.rule_evidence_map import (
    RULE_AFFECTED_PART,
    RULE_TITLES,
)
from app.modules.parser.analyzers.image_analyzer import is_broken_image


_MAX_DEPTH = 5
_MAX_ITEMS = 25
_MAX_STRING_LENGTH = 2_000
_INTERNAL_EVIDENCE_KEY = "_evidence_v1"
_EXPECTED_KEYS = (
    "expected",
    "expected_value",
    "expected_values",
    "ideal",
    "ideal_value",
    "ideal_values",
    "expected_threshold",
)
_TARGET_KEYS = (
    "attribute",
    "css_selector",
    "element",
    "endpoint",
    "header",
    "header_name",
    "href",
    "path",
    "resource_url",
    "selector",
    "src",
    "tag",
    "tag_name",
    "url",
    "xpath",
)

RULE_EVIDENCE_LOCATORS: Dict[str, Dict[str, str]] = {
    "on_page_001": {"element": "title", "selector": "head > title"},
    "on_page_002": {
        "element": "meta",
        "selector": 'head > meta[name="description"]',
        "attribute": "content",
    },
    "on_page_003": {"element": "h1", "selector": "h1"},
    "on_page_006": {
        "element": "link",
        "selector": 'head > link[rel="canonical"]',
        "attribute": "href",
    },
    "technical_002": {
        "element": "meta",
        "selector": 'head > meta[name="viewport"]',
        "attribute": "content",
    },
    "mobile_001": {
        "element": "meta",
        "selector": 'head > meta[name="viewport"]',
        "attribute": "content",
    },
    "images_001": {"element": "img", "attribute": "alt"},
    "images_013": {"element": "img", "attribute": "src"},
    "schema_001": {
        "element": "script",
        "selector": 'script[type="application/ld+json"]',
    },
    "security_005": {"signal": "HTTP Strict-Transport-Security response header"},
    "technical_007": {"signal": "HTTP response security headers"},
    "perf_001": {"signal": "HTTP response time"},
}

_CONTEXT_PATHS: Dict[str, tuple[str, ...]] = {
    "on_page_001": ("basic.title", "basic.title_length"),
    "on_page_002": ("basic.meta_description", "basic.meta_description_length"),
    "on_page_003": ("headings.h1", "basic.headings"),
    "on_page_006": ("basic.canonical",),
    "technical_002": ("basic.viewport",),
    "mobile_001": ("basic.viewport",),
    "technical_007": ("http.headers",),
    "security_003": ("http.headers",),
    "security_005": ("http.headers",),
    "security_004": ("ssl",),
    "perf_001": ("http.response_time_ms",),
    "links_003": ("links",),
    "images_001": ("images",),
    "images_013": ("broken_images",),
    "schema_001": ("schemas", "structured_data"),
    "content_001": ("basic.word_count",),
    "a11y_001": ("forms",),
    "url_structure_001": ("url",),
}


class EvidenceTarget(BaseModel):
    """Where the rule looked, plus any exact locator returned by the rule."""

    url: Optional[str] = None
    part: str
    resource_urls: Optional[List[str]] = None
    identifiers: Dict[str, Any] = Field(default_factory=dict)
    mapping_status: Literal["registered", "fallback"] = "registered"


class EvidenceSource(BaseModel):
    """Origin of the observed facts."""

    kind: Literal["rule_result_data", "page_context", "unavailable"]


class RuleEvidenceV1(BaseModel):
    """Stable evidence contract; legacy rule data remains separately available."""

    schema_version: Literal["1.0"] = "1.0"
    rule_id: str
    rule_name: str
    category: str
    outcome: Literal["passed", "failed", "error"]
    target: EvidenceTarget
    observed: Optional[Any] = None
    expected: Optional[Dict[str, Any]] = None
    evidence_status: Literal["available", "unavailable"]
    source: EvidenceSource
    message: Optional[str] = None
    fix_location: Optional[EvidenceTarget] = None
    recommendation: Optional[str] = None


class RuleEvidenceExtractor:
    """Normalize rule-produced facts without inventing missing observations."""

    @staticmethod
    def build_page_context(
        *,
        seo_data: Any = None,
        network_data: Any = None,
        parsed_data: Optional[Dict[str, Any]] = None,
        crawl_page: Any = None,
    ) -> Dict[str, Any]:
        """Expose persisted page facts in the paths used by evidence mappings."""
        parsed_data = parsed_data if isinstance(parsed_data, dict) else {}
        basic: Dict[str, Any] = {}
        for field in (
            "title",
            "title_length",
            "meta_description",
            "meta_description_length",
            "canonical",
            "robots_meta",
            "viewport",
            "word_count",
            "headings",
        ):
            value = getattr(seo_data, field, None) if seo_data else None
            if value is not None:
                basic[field] = value

        raw_images = parsed_data.get("images") or parsed_data.get("images_rendered") or []
        broken_images = [
            image for image in raw_images
            if (
                isinstance(image, dict)
                and (
                    image.get("tag") in ("img", "source")
                    or (not image.get("tag") and image.get("url"))
                )
                and is_broken_image(image)
            )
        ] if isinstance(raw_images, list) else []
        context: Dict[str, Any] = {
            "basic": basic,
            "headings": parsed_data.get("headings") or {},
            "links": parsed_data.get("links") or {},
            "images": raw_images,
            "broken_images": broken_images,
            "schemas": parsed_data.get("schemas") or [],
            "structured_data": parsed_data.get("structured_data") or {},
            "forms": parsed_data.get("forms") or [],
            "technical": parsed_data.get("technical") or {},
            "content": parsed_data.get("content") or {},
            "url": {},
            "http": {},
            "ssl": {},
        }

        if network_data:
            context["http"] = {
                "headers": network_data.headers or {},
                "response_time_ms": network_data.response_time_ms,
                "status_code": network_data.status_code,
            }
            context["ssl"] = network_data.security or {}
            context["performance"] = network_data.performance or {}
        if crawl_page:
            context["url"] = {
                "url": crawl_page.url,
                "normalized_url": crawl_page.normalized_url,
                "final_url": crawl_page.final_url,
                "status_code": crawl_page.status_code,
                "path": crawl_page.path,
            }
        return context

    @classmethod
    def build(
        cls,
        *,
        rule_id: str,
        rule_name: str,
        category: str,
        passed: bool,
        severity: str,
        message: Optional[str],
        recommendation: Optional[str],
        page_url: Optional[str],
        rule_data: Any,
        page_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = cls._without_internal_fields(rule_data)
        context_facts = cls._context_facts(rule_id, page_context or {})
        has_rule_data = bool(data)
        has_context = bool(context_facts)

        if has_rule_data:
            observed = cls._bounded(data)
            source = EvidenceSource(
                kind="rule_result_data",
            )
        elif has_context:
            observed = cls._bounded(context_facts)
            source = EvidenceSource(
                kind="page_context",
            )
        else:
            observed = None
            source = EvidenceSource(kind="unavailable")

        expected = {
            key: cls._bounded(data[key])
            for key in _EXPECTED_KEYS
            if key in data
        } or None
        target = cls._target(rule_id, page_url, data, context_facts)
        outcome = "error" if severity == "error" else ("passed" if passed else "failed")

        record = RuleEvidenceV1(
            rule_id=rule_id,
            rule_name=rule_name or RULE_TITLES.get(rule_id, rule_id),
            category=category or "unknown",
            outcome=outcome,
            target=target,
            observed=observed,
            expected=expected,
            evidence_status="available" if has_rule_data or has_context else "unavailable",
            source=source,
            message=message,
            fix_location=target if outcome == "failed" else None,
            recommendation=recommendation if outcome == "failed" else None,
        )
        return record.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _without_internal_fields(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {
            key: item for key, item in value.items()
            if key != _INTERNAL_EVIDENCE_KEY
        }

    @classmethod
    def _target(
        cls,
        rule_id: str,
        page_url: Optional[str],
        data: Dict[str, Any],
        context_facts: Optional[Dict[str, Any]] = None,
    ) -> EvidenceTarget:
        part = RULE_AFFECTED_PART.get(rule_id)
        mapping_status: Literal["registered", "fallback"] = (
            "registered" if part else "fallback"
        )
        identifiers = dict(RULE_EVIDENCE_LOCATORS.get(rule_id, {}))
        resource_urls: List[str] = []
        if rule_id == "images_013":
            broken_images = data.get("broken_images")
            if not isinstance(broken_images, list) or not broken_images:
                broken_images = (context_facts or {}).get("broken_images", [])
            if isinstance(broken_images, list):
                for image in broken_images:
                    if not isinstance(image, dict):
                        continue
                    resource_url = image.get("url") or image.get("src")
                    if isinstance(resource_url, str) and resource_url.strip():
                        resource_urls.append(resource_url.strip())
        for key in _TARGET_KEYS:
            value = data.get(key)
            if isinstance(value, (str, int, float, bool)) and value != "":
                identifiers.setdefault(key, value)
        return EvidenceTarget(
            url=page_url,
            part=part or rule_id,
            resource_urls=list(dict.fromkeys(resource_urls)) or None,
            identifiers=identifiers,
            mapping_status=mapping_status,
        )

    @classmethod
    def _context_facts(
        cls, rule_id: str, page_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        facts: Dict[str, Any] = {}
        for path in _CONTEXT_PATHS.get(rule_id, ()):
            value: Any = page_context
            for segment in path.split("."):
                if not isinstance(value, dict) or segment not in value:
                    value = None
                    break
                value = value[segment]
            if value is not None:
                facts[path] = value
        return facts

    @classmethod
    def _bounded(cls, value: Any, depth: int = 0) -> Any:
        value = jsonable_encoder(value)
        if isinstance(value, str):
            if len(value) <= _MAX_STRING_LENGTH:
                return value
            return {
                "value": value[:_MAX_STRING_LENGTH],
                "truncated": True,
                "original_length": len(value),
            }
        if isinstance(value, dict):
            if depth >= _MAX_DEPTH:
                return {"truncated": True}
            entries = list(value.items())
            output = {
                str(key): cls._bounded(item, depth + 1)
                for key, item in entries[:_MAX_ITEMS]
            }
            if len(entries) > _MAX_ITEMS:
                output["_truncated_items"] = len(entries) - _MAX_ITEMS
            return output
        if isinstance(value, list):
            if depth >= _MAX_DEPTH:
                return [{"truncated": True}] if value else []
            output = [cls._bounded(item, depth + 1) for item in value[:_MAX_ITEMS]]
            if len(value) > _MAX_ITEMS:
                output.append({"_truncated_items": len(value) - _MAX_ITEMS})
            return output
        return value


def legacy_rule_data(rule_data: Any) -> Dict[str, Any]:
    """Return original rule fields without evidence-extractor internals."""
    return RuleEvidenceExtractor._without_internal_fields(rule_data)

