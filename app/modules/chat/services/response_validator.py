import json
from typing import Any

from app.modules.chat.schemas.response import ChatReference


class ResponseValidator:
    def validate(self, answer: str, tool_messages: list[Any]) -> dict:
        references: list[ChatReference] = []
        seen: set[tuple] = set()
        for msg in tool_messages:
            try:
                data = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                ref_type = "rule" if "rule_id" in item else ("page" if "page_url" in item else "category")
                key = (ref_type, item.get("rule_id"), item.get("page_url"))
                if key and key not in seen:
                    seen.add(key)
                    references.append(ChatReference(
                        type=ref_type,
                        rule_id=item.get("rule_id"),
                        page_url=item.get("page_url"),
                        category=item.get("category"),
                    ))
        return {"answer": answer, "references": references}
