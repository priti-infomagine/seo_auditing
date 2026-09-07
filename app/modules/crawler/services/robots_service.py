"""
RobotsService - Parses robots.txt directives and evaluates crawl permissions per user-agent.
"""
from typing import Dict, List, Optional
from urllib.parse import urlparse
import httpx


class RobotsRuleGroup:
    def __init__(self, user_agents: List[str]):
        self.user_agents = [ua.lower() for ua in user_agents]
        self.allow_patterns: List[str] = []
        self.disallow_patterns: List[str] = []

    def matches_user_agent(self, user_agent: str) -> bool:
        ua_clean = user_agent.lower()
        return any(ua in ua_clean or ua == "*" for ua in self.user_agents)


class RobotsPolicy:
    def __init__(self, raw_text: str = ""):
        self.raw_text = raw_text
        self.groups: List[RobotsRuleGroup] = []
        self.sitemaps: List[str] = []
        self.crawl_delay: Optional[int] = None
        self._parse(raw_text)

    def _parse(self, content: str) -> None:
        if not content:
            return

        current_agents: List[str] = []
        current_group: Optional[RobotsRuleGroup] = None

        for line in content.splitlines():
            clean = line.split("#", 1)[0].strip()
            if not clean:
                continue

            if ":" not in clean:
                continue

            key, value = clean.split(":", 1)
            key = key.strip().lower()
            val = value.strip()

            if key == "user-agent":
                if current_group and current_agents:
                    self.groups.append(current_group)
                    current_group = None
                    current_agents = []
                current_agents.append(val)
            elif key in ("allow", "disallow"):
                if not current_group:
                    current_group = RobotsRuleGroup(current_agents if current_agents else ["*"])
                if key == "allow" and val:
                    current_group.allow_patterns.append(val)
                elif key == "disallow" and val:
                    current_group.disallow_patterns.append(val)
            elif key == "sitemap" and val:
                self.sitemaps.append(val)
            elif key == "crawl-delay" and val.isdigit():
                self.crawl_delay = int(val)

        if current_group:
            self.groups.append(current_group)

    def is_allowed(self, path: str, user_agent: str = "*") -> bool:
        """Evaluate path against matched group rules."""
        if not path:
            path = "/"

        matched_groups = [g for g in self.groups if g.matches_user_agent(user_agent)]
        if not matched_groups:
            return True

        # Check disallow / allow precedence (longest matching pattern wins)
        longest_match_len = -1
        allowed = True

        for group in matched_groups:
            for pattern in group.disallow_patterns:
                if pattern and self._path_matches(path, pattern):
                    if len(pattern) > longest_match_len:
                        longest_match_len = len(pattern)
                        allowed = False
            for pattern in group.allow_patterns:
                if pattern and self._path_matches(path, pattern):
                    if len(pattern) >= longest_match_len:
                        longest_match_len = len(pattern)
                        allowed = True

        return allowed

    def _path_matches(self, path: str, pattern: str) -> bool:
        if pattern == "/":
            return True
        if pattern.endswith("$"):
            return path == pattern[:-1]
        return path.startswith(pattern.rstrip("*"))


class RobotsService:
    """Fetches, parses, and caches robots.txt rules for a site domain."""

    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self.policies: Dict[str, RobotsPolicy] = {}

    async def fetch_policy(self, start_url: str, timeout: float = 10.0) -> RobotsPolicy:
        parsed = urlparse(start_url)
        domain = parsed.netloc.lower()
        if domain in self.policies:
            return self.policies[domain]

        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(robots_url)
                if resp.status_code == 200:
                    policy = RobotsPolicy(resp.text)
                else:
                    policy = RobotsPolicy("")
        except Exception:
            policy = RobotsPolicy("")

        self.policies[domain] = policy
        return policy

    def is_allowed(self, url: str, policy: RobotsPolicy) -> bool:
        parsed = urlparse(url)
        return policy.is_allowed(parsed.path or "/", user_agent=self.user_agent)
