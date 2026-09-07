from .text_normalizer import normalize_text


def normalize_heading_text(text: str) -> str:
    return normalize_text(text)


def normalize_headings(headings: list[dict]) -> list[dict]:
    result = []
    for idx, heading in enumerate(headings):
        result.append({
            "level": heading.get("level", 0),
            "text": normalize_heading_text(heading.get("text", "")),
            "position": idx,
        })
    return result
