from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.datetime_utils import utc_now


class ParsedPageStorage:
    """
    Storage abstraction for parsed page artifacts.

    Currently writes to local filesystem. Can be swapped for S3-compatible
    storage without changing parser logic.
    """

    def __init__(self, base_dir: str = "app/storage/parsed"):
        self.base_dir = Path(base_dir)

    def save(self, domain: str, data: dict[str, Any]) -> tuple[Path, int]:
        domain_dir = self.base_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        test_number = self._next_test_number(domain)
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        filepath = domain_dir / f"{domain}_test_{test_number}_{timestamp}.json"

        import json
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return filepath, test_number

    def _next_test_number(self, domain: str) -> int:
        import re
        domain_dir = self.base_dir / domain
        if not domain_dir.exists():
            return 1
        test_numbers = []
        for fp in domain_dir.glob(f"{domain}_test_*.json"):
            m = re.search(r"_test_(\d+)", fp.stem)
            if m:
                test_numbers.append(int(m.group(1)))
        return max(test_numbers, default=0) + 1

    def load(self, domain: str, test_number: int) -> dict[str, Any] | None:
        import re
        domain_dir = self.base_dir / domain
        if not domain_dir.exists():
            return None
        for fp in domain_dir.glob(f"{domain}_test_{test_number}_*.json"):
            import json
            with fp.open("r", encoding="utf-8") as f:
                return json.load(f)
        return None
