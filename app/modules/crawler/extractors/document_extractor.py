"""
Document extractor - owns HTML parsing and DOM foundation.
"""
from dataclasses import dataclass, field
from bs4 import BeautifulSoup


@dataclass
class DocumentFacts:
    soup: BeautifulSoup
    language: str = ""
    charset: str = ""
    doctype: str = ""
    base_url: str = ""
    is_html: bool = True
    raw_html: str = ""


def extract_document(html: str, url: str) -> DocumentFacts:
    if not html:
        return DocumentFacts(soup=BeautifulSoup("", "html.parser"), is_html=False, raw_html=html)

    soup = BeautifulSoup(html, "html.parser")
    is_html = soup.find("html") is not None

    language = ""
    html_tag = soup.find("html")
    if html_tag:
        language = html_tag.get("lang", "").strip()

    charset = ""
    charset_meta = soup.find("meta", attrs={"charset": True})
    if charset_meta:
        charset = charset_meta.get("charset", "").strip().lower()
    else:
        content_type_meta = soup.find("meta", attrs={"http-equiv": "Content-Type"})
        if content_type_meta:
            content = content_type_meta.get("content", "")
            if "charset=" in content:
                charset = content.split("charset=")[-1].strip().lower()

    doctype = ""
    if html.strip().upper().startswith("<!DOCTYPE"):
        doctype_end = html.find(">", 10)
        if doctype_end != -1:
            doctype = html[10:doctype_end].strip()

    return DocumentFacts(
        soup=soup,
        language=language,
        charset=charset,
        doctype=doctype,
        base_url=url,
        is_html=is_html,
        raw_html=html,
    )
