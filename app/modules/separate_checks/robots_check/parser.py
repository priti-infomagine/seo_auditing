"""
Robots.txt parser built on top of the ``protego`` library.

``protego`` implements RFC 9309 and is more spec-correct than the stdlib's
``urllib.robotparser``. This module translates its internal rule model into
the ``ParsedRobots`` dataclass consumed by the evaluator.
"""
from typing import Optional

from protego import Protego

from app.core.logger import logger

from .fetcher import ParsedRobots


def parse_robots_txt(raw_text: str) -> ParsedRobots:
    """Parse raw ``robots.txt`` text into a :class:`ParsedRobots`.

    Non-blocking: any parse error is captured as a ``syntax_warning`` and
    the parser returns an empty result set rather than raising.

    Args:
        raw_text: The raw robots.txt body.

    Returns:
        A :class:`ParsedRobots` with user-agent groups, sitemaps, crawl-delay,
        syntax warnings, and the original text.
    """
    if not raw_text or not raw_text.strip():
        return ParsedRobots(raw_text=raw_text or "")

    syntax_warnings: list[str] = []
    user_agent_groups: list[dict] = []
    sitemaps: list[str] = []
    crawl_delay: Optional[int] = None

    try:
        parser = Protego.parse(raw_text)

        sitemaps = list(parser.sitemaps)

        max_delay: Optional[int] = None
        for ua_name, ruleset in parser._user_agents.items():
            disallow_paths: list[str] = []
            allow_paths: list[str] = []
            for rule in ruleset._rules:
                field = rule.field
                value = rule.value
                pattern = (
                    value._pattern
                    if hasattr(value, "_pattern")
                    else str(value)
                )
                if not pattern:
                    if field == "disallow":
                        syntax_warnings.append(
                            "Blank Disallow directive (treats as allow-all)"
                        )
                    continue
                if field == "disallow":
                    disallow_paths.append(pattern)
                elif field == "allow":
                    allow_paths.append(pattern)

            delay = ruleset.crawl_delay
            if delay is not None:
                if max_delay is None or delay > max_delay:
                    max_delay = delay

            user_agent_groups.append(
                {
                    "user_agents": [ua_name],
                    "disallow": disallow_paths,
                    "allow": allow_paths,
                    "crawl_delay": delay,
                }
            )

        crawl_delay = max_delay

        if parser._invalid_directive_seen and parser._invalid_directive_seen > 0:
            syntax_warnings.append(
                f"Encountered {parser._invalid_directive_seen} invalid/unknown directive(s)"
            )

        # Detect blank Disallow directives in raw text for syntax warning
        for line in raw_text.splitlines():
            stripped = line.strip().lower()
            if stripped == "disallow:" or stripped == "disallow: " or stripped.startswith("disallow:"):
                parts = stripped.split(":", 1)
                if len(parts) == 2 and parts[1].strip() == "":
                    if "Blank Disallow directive" not in syntax_warnings:
                        syntax_warnings.append(
                            "Blank Disallow directive (treats as allow-all)"
                        )

    except Exception as exc:
        logger.warning("parse_robots_txt: protego parse failure: %s", exc)
        return ParsedRobots(
            user_agent_groups=[],
            sitemaps=[],
            crawl_delay=None,
            syntax_warnings=[f"Parse error: {exc}"],
            raw_text=raw_text,
        )

    return ParsedRobots(
        user_agent_groups=user_agent_groups,
        sitemaps=sitemaps,
        crawl_delay=crawl_delay,
        syntax_warnings=syntax_warnings,
        raw_text=raw_text,
    )
