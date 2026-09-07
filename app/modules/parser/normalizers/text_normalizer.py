import html
import re


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def unescape_html(text: str) -> str:
    return html.unescape(text)


def strip_zero_width(text: str) -> str:
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)


def normalize_text(text: str) -> str:
    text = unescape_html(text)
    text = strip_zero_width(text)
    return normalize_whitespace(text)
