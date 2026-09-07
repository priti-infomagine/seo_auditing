from .text_normalizer import normalize_text


def normalize_meta_tag_content(content: str) -> str:
    if not content:
        return ""
    return normalize_text(content)


def normalize_title(title: str) -> str:
    if not title:
        return ""
    return normalize_text(title)


def normalize_description(description: str) -> str:
    if not description:
        return ""
    return normalize_text(description)


def normalize_canonical(canonical: str) -> str:
    if not canonical:
        return ""
    return canonical.strip()
