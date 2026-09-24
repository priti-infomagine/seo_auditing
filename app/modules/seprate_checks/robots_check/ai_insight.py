"""
AI-generated recommendations for robots.txt findings via Ollama.

Reuses the exact Ollama call pattern from
``audit_response_builder._generate_ollama_recommendation``: same endpoint,
same payload shape, same graceful degradation to template-based fallback
text when Ollama is unavailable.
"""
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import logger

from .fetcher import FetchResult, ParsedRobots, Evaluation

_TEMPLATE_MAP: dict[str, str] = {
    "robots_site_block": (
        "Remove the `Disallow: /` directive from the wildcard user-agent "
        "group in robots.txt to allow search engines to index your site."
    ),
    "robots_asset_block": (
        "Unblock CSS and JavaScript file paths in robots.txt so search engines "
        "can properly render and index your pages."
    ),
    "robots_sitemap_declared": (
        "Add a `Sitemap:` directive in robots.txt pointing to your XML sitemap."
    ),
    "robots_sitemap_reachable": (
        "Fix or remove unreachable sitemap URLs declared in robots.txt, or "
        "verify the sitemap is accessible over HTTP."
    ),
    "robots_missing": (
        "Create a robots.txt file at the root of your domain "
        "(https://domain.com/robots.txt) to control crawler access."
    ),
    "robots_unreachable": (
        "Ensure robots.txt is accessible at https://domain.com/robots.txt "
        "and returns a 200 status code."
    ),
    "robots_syntax": (
        "Fix the malformed directives in robots.txt to ensure crawlers "
        "interpret your rules correctly."
    ),
    "robots_oversized": (
        "Reduce the size of robots.txt to under 500 KB so all rules are "
        "processed by search engine crawlers."
    ),
}


def _template_for_code(code: str) -> str:
    return _TEMPLATE_MAP.get(
        code,
        "Review and fix issues in your robots.txt configuration.",
    )


def recommendation_for_code(code: str) -> str:
    """Return the deterministic fallback recommendation for a finding code."""
    return _template_for_code(code)


def _build_ollama_prompt(
    title: str,
    what: Optional[str],
    why: Optional[str],
) -> str:
    prompt = (
        f"You are an expert technical SEO auditor. Write a single clear, "
        f"actionable, professional recommendation (1-2 sentences max) to "
        f"fix the following issue.\n"
        f"Issue Title: {title}\n"
    )
    if what:
        prompt += f"Problem (What): {what}\n"
    if why:
        prompt += f"Impact (Why): {why}\n"
    prompt += "Do not include conversational intros or extra text. Provide ONLY the recommendation statement."
    return prompt


async def _ollama_recommendation(
    title: str,
    what: Optional[str],
    why: Optional[str],
    default_rec: Optional[str],
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[object] = None,
) -> Optional[str]:
    prompt = _build_ollama_prompt(title, what, why)

    async def _call():
        try:
            url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
            payload = {
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 100,
                },
            }
            timeout = min(10.0, float(settings.OLLAMA_TIMEOUT))
            if client:
                resp = await client.post(url, json=payload, timeout=timeout)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await c.post(url, json=payload, timeout=timeout)

            if resp.status_code == 200:
                data = resp.json()
                text = data.get("response", "").strip()
                if text:
                    return text
        except Exception as exc:
            logger.warning(
                "ai_insight: Ollama failed for %r: %s", title, exc
            )
        return default_rec or None

    if semaphore is not None:
        async with semaphore:
            return await _call()
    return await _call()


async def generate_insights(
    evaluation: Evaluation,
    fetch_result: FetchResult,
    parsed: Optional[ParsedRobots],
) -> dict:
    """Generate ``why`` and ``recommendation`` text for the evaluation.

    Falls back to templates on any Ollama failure.
    """
    findings = evaluation.findings or []
    if not findings:
        return {"why": None, "recommendation": None}

    primary_code = findings[0]["code"]
    primary_title = _code_to_title(primary_code)

    why = None
    recommendation = None

    try:
        recommendation = await _ollama_recommendation(
            title=primary_title,
            what=evaluation.evidence_str,
            why=None,
            default_rec=_template_for_code(primary_code),
        )
    except Exception as exc:
        logger.warning("ai_insight: generation failed: %s", exc)
        recommendation = _template_for_code(primary_code)

    if evaluation.evidence_str:
        why = evaluation.evidence_str

    return {
        "why": why,
        "recommendation": recommendation,
    }


def _code_to_title(code: str) -> str:
    """Map a finding code to a human-readable title."""
    mapping: dict[str, str] = {
        "robots_site_block": "Robots.txt blocks all crawlers",
        "robots_asset_block": "Robots.txt blocks static assets",
        "robots_sitemap_declared": "No sitemap declared in robots.txt",
        "robots_sitemap_reachable": "Sitemap URLs unreachable",
        "robots_missing": "Robots.txt not configured",
        "robots_unreachable": "Robots.txt could not be fetched",
        "robots_syntax": "Syntax issues in robots.txt",
        "robots_oversized": "Robots.txt exceeds recommended size",
        "robots_ok": "Robots.txt is properly configured",
    }
    return mapping.get(code, code)
