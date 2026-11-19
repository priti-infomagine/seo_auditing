from __future__ import annotations

import copy
import re

from bs4 import BeautifulSoup

from app.modules.parser.models.content_data import (
    ContentData,
    HeadingData,
    ParagraphData,
    ListData,
    TableData,
    SemanticElement,
    FormData,
    FormFieldData,
    ButtonData,
    SkipLinkData,
    LandmarkData,
)
from app.modules.parser.services.document_parser_service import DocumentContext


class ContentExtractor:
    """
    Extracts visible text and content structure.

    Works on a copy of the DOM so the original is not mutated.
    """

    def extract(self, context: DocumentContext) -> ContentData:
        soup = context.soup

        text = self._get_visible_text(soup)
        normalized_text = self._normalize_text(text)

        return ContentData(
            text=text,
            normalized_text=normalized_text,
            word_count=self._word_count(normalized_text),
            character_count=len(normalized_text),
            paragraphs=self._paragraphs(soup),
            headings=self._headings(soup),
            lists=self._lists(soup),
            tables=self._tables(soup),
            semantic_elements=self._semantic_elements(soup),
            has_main=soup.find("main") is not None,
            has_article=soup.find("article") is not None,
            has_header=soup.find("header") is not None,
            has_footer=soup.find("footer") is not None,
            has_nav=soup.find("nav") is not None,
            forms=self._forms(soup),
            buttons=self._buttons(soup),
            skip_links=self._skip_links(soup),
            landmarks=self._landmarks(soup),
            aria_attributes=self._aria_attributes(soup),
        )

    @staticmethod
    def _get_visible_text(soup: BeautifulSoup) -> str:
        working = copy.copy(soup)
        for tag in working(["script", "style", "noscript", "template"]):
            tag.decompose()
        return working.get_text(" ", strip=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _word_count(text: str) -> int:
        if not text:
            return 0
        return len(text.split())

    @staticmethod
    def _paragraphs(soup: BeautifulSoup):
        return [
            ParagraphData(text=tag.get_text(" ", strip=True))
            for tag in soup.find_all("p")
            if tag.get_text(" ", strip=True)
        ]

    @staticmethod
    def _headings(soup: BeautifulSoup):
        results = []
        position = 0
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            results.append(
                HeadingData(
                    level=int(tag.name[1]),
                    text=text,
                    position=position,
                )
            )
            position += 1
        return results

    @staticmethod
    def _lists(soup: BeautifulSoup):
        results = []
        for tag in soup.find_all(["ul", "ol"]):
            items = [
                item.get_text(" ", strip=True)
                for item in tag.find_all("li", recursive=False)
            ]
            results.append(
                ListData(
                    ordered=tag.name == "ol",
                    items=items,
                )
            )
        return results

    @staticmethod
    def _tables(soup: BeautifulSoup):
        results = []
        for table in soup.find_all("table"):
            headers = [
                cell.get_text(" ", strip=True)
                for cell in table.find_all("th")
            ]
            rows = []
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if not cells:
                    continue
                rows.append([
                    cell.get_text(" ", strip=True)
                    for cell in cells
                ])
            results.append(
                TableData(
                    headers=headers,
                    rows=rows,
                )
            )
        return results

    @staticmethod
    def _semantic_elements(soup: BeautifulSoup):
        tags = [
            "main", "article", "section", "nav", "header",
            "footer", "aside", "figure", "figcaption", "address", "time",
        ]
        return [
            SemanticElement(
                tag=tag.name,
                text=tag.get_text(" ", strip=True),
            )
            for tag in soup.find_all(tags)
        ]

    def _forms(self, soup: BeautifulSoup) -> list[FormData]:
        """Extract form elements with their fields and labels."""
        forms = []
        for form in soup.find_all("form"):
            form_data = FormData(
                action=form.get("action", "").strip(),
                method=form.get("method", "get").strip().lower(),
                id=form.get("id", "").strip(),
                name=form.get("name", "").strip(),
            )

            # Extract form fields
            field_tags = form.find_all(["input", "select", "textarea", "button"])
            for field in field_tags:
                if field.name == "input" and field.get("type", "").lower() in ("hidden", "submit", "button", "reset", "image"):
                    # Skip hidden and button-type inputs (handled in buttons)
                    continue

                field_data = self._extract_form_field(field, form, soup)
                form_data.fields.append(field_data)

            # Extract fieldsets
            for fieldset in form.find_all("fieldset"):
                legend = fieldset.find("legend")
                fieldset_data = {
                    "legend": legend.get_text(" ", strip=True) if legend else "",
                    "fields": [],
                }
                for field in fieldset.find_all(["input", "select", "textarea"]):
                    if field.get("type", "").lower() == "hidden":
                        continue
                    field_data = self._extract_form_field(field, form, soup)
                    fieldset_data["fields"].append(field_data.model_dump())
                form_data.fieldsets.append(fieldset_data)

            forms.append(form_data)

        return forms

    def _extract_form_field(self, field, form: BeautifulSoup, soup: BeautifulSoup) -> FormFieldData:
        """Extract individual form field with label associations."""
        field_id = field.get("id", "").strip()
        field_name = field.get("name", "").strip()
        field_type = field.get("type", "").strip().lower() if field.name == "input" else field.name

        # Check for wrapping label
        wrapping_label = field.find_parent("label")
        has_wrapping_label = wrapping_label is not None
        label_text = ""
        if has_wrapping_label:
            label_text = wrapping_label.get_text(" ", strip=True)

        # Check for label[for] association
        has_label_for = False
        if field_id:
            label_for = form.find("label", attrs={"for": field_id}) or soup.find("label", attrs={"for": field_id})
            if label_for:
                has_label_for = True
                if not label_text:
                    label_text = label_for.get_text(" ", strip=True)

        # ARIA attributes
        aria_label = field.get("aria-label", "").strip()
        aria_labelledby = field.get("aria-labelledby", "").strip()
        aria_describedby = field.get("aria-describedby", "").strip()

        # Compute accessible name per WCAG
        accessible_name = ""
        accessible_name_source = ""

        if aria_label:
            accessible_name = aria_label
            accessible_name_source = "aria-label"
        elif aria_labelledby:
            # Would need to resolve ID refs - simplified
            accessible_name = f"[referenced by aria-labelledby: {aria_labelledby}]"
            accessible_name_source = "aria-labelledby"
        elif label_text:
            accessible_name = label_text
            accessible_name_source = "label" if has_label_for else "wrapping-label"
        elif field.get("title", "").strip():
            accessible_name = field.get("title", "").strip()
            accessible_name_source = "title"
        elif field_type in ("submit", "button", "reset", "image") and field.get("value", "").strip():
            accessible_name = field.get("value", "").strip()
            accessible_name_source = "value"
        elif field.get("placeholder", "").strip():
            accessible_name = field.get("placeholder", "").strip()
            accessible_name_source = "placeholder"

        return FormFieldData(
            tag=field.name,
            type=field_type,
            name=field_name,
            id=field_id,
            label_text=label_text,
            has_label_for=has_label_for,
            has_wrapping_label=has_wrapping_label,
            aria_label=aria_label,
            aria_labelledby=aria_labelledby,
            aria_describedby=aria_describedby,
            required=field.get("required") is not None,
            disabled=field.get("disabled") is not None,
            readonly=field.get("readonly") is not None,
            placeholder=field.get("placeholder", "").strip(),
            title=field.get("title", "").strip(),
            accessible_name=accessible_name,
            accessible_name_source=accessible_name_source,
        )

    def _buttons(self, soup: BeautifulSoup) -> list[ButtonData]:
        """Extract button elements and their accessible names."""
        buttons = []
        # Find all button elements and input buttons
        button_elements = soup.find_all("button")
        button_elements.extend(soup.find_all("input", attrs={"type": ["button", "submit", "reset", "image"]}))

        for btn in button_elements:
            tag_name = btn.name
            btn_type = btn.get("type", "").strip().lower() if tag_name == "input" else "button"
            btn_id = btn.get("id", "").strip()
            btn_name = btn.get("name", "").strip()

            # Get text content for button elements
            text_content = ""
            if tag_name == "button":
                text_content = btn.get_text(" ", strip=True)
            else:
                text_content = btn.get("value", "").strip()

            # ARIA attributes
            aria_label = btn.get("aria-label", "").strip()
            aria_labelledby = btn.get("aria-labelledby", "").strip()
            title = btn.get("title", "").strip()

            # Compute accessible name per WCAG
            accessible_name = ""
            accessible_name_source = ""

            if aria_label:
                accessible_name = aria_label
                accessible_name_source = "aria-label"
            elif aria_labelledby:
                accessible_name = f"[referenced by aria-labelledby: {aria_labelledby}]"
                accessible_name_source = "aria-labelledby"
            elif text_content:
                accessible_name = text_content
                accessible_name_source = "content"
            elif btn_type == "image" and btn.get("alt", "").strip():
                accessible_name = btn.get("alt", "").strip()
                accessible_name_source = "alt"
            elif title:
                accessible_name = title
                accessible_name_source = "title"
            elif btn.get("value", "").strip():
                accessible_name = btn.get("value", "").strip()
                accessible_name_source = "value"

            buttons.append(ButtonData(
                tag=tag_name,
                type=btn_type,
                id=btn_id,
                name=btn_name,
                text_content=text_content,
                value=btn.get("value", "").strip(),
                aria_label=aria_label,
                aria_labelledby=aria_labelledby,
                title=title,
                accessible_name=accessible_name,
                accessible_name_source=accessible_name_source,
                has_accessible_name=bool(accessible_name),
            ))

        return buttons

    def _skip_links(self, soup: BeautifulSoup) -> list[SkipLinkData]:
        """Extract skip navigation links."""
        skip_links = []

        # Find all anchor links that could be skip links
        for idx, link in enumerate(soup.find_all("a", href=True)):
            href = link.get("href", "").strip()
            text = link.get_text(" ", strip=True)

            # Check if it's a skip link (href starts with # and targets main content)
            is_skip = False
            if href.startswith("#"):
                target_id = href[1:]
                # Common skip link targets
                if target_id in ("main", "content", "main-content", "skip-to-content", "skipnav", "maincontent"):
                    is_skip = True
                # Check if target element exists and is a main content area
                elif soup.find(id=target_id):
                    target = soup.find(id=target_id)
                    if target and target.name in ("main", "article", "section", "div"):
                        is_skip = True

            # Also check for skip link classes
            classes = link.get("class", [])
            if isinstance(classes, str):
                classes = classes.split()
            if any("skip" in c.lower() for c in classes):
                is_skip = True

            if is_skip:
                # Check if it's the first focusable element (heuristic)
                is_first = idx == 0  # Simplified - would need more complex analysis

                skip_links.append(SkipLinkData(
                    href=href,
                    text=text,
                    is_first_focusable=is_first,
                    position=idx,
                ))

        return skip_links

    def _landmarks(self, soup: BeautifulSoup) -> list[LandmarkData]:
        """Extract landmark regions (HTML5 semantic + ARIA roles)."""
        landmarks = []

        # HTML5 semantic elements that are landmarks
        landmark_elements = {
            "main": "main",
            "nav": "navigation",
            "header": "banner",
            "footer": "contentinfo",
            "aside": "complementary",
            "section": "region",
            "form": "form",
            "article": "article",
        }

        for tag_name, landmark_type in landmark_elements.items():
            for elem in soup.find_all(tag_name):
                aria_label = elem.get("aria-label", "").strip()
                aria_labelledby = elem.get("aria-labelledby", "").strip()
                has_name = bool(aria_label or aria_labelledby)

                landmarks.append(LandmarkData(
                    type=landmark_type,
                    element=tag_name,
                    role="",
                    aria_label=aria_label,
                    aria_labelledby=aria_labelledby,
                    has_accessible_name=has_name,
                ))

        # ARIA role landmarks
        aria_landmark_roles = {
            "banner", "navigation", "main", "complementary",
            "contentinfo", "search", "form", "region"
        }

        for elem in soup.find_all(attrs={"role": True}):
            role = elem.get("role", "").strip().lower()
            if role in aria_landmark_roles:
                aria_label = elem.get("aria-label", "").strip()
                aria_labelledby = elem.get("aria-labelledby", "").strip()
                has_name = bool(aria_label or aria_labelledby)

                landmarks.append(LandmarkData(
                    type=role,
                    element=elem.name,
                    role=role,
                    aria_label=aria_label,
                    aria_labelledby=aria_labelledby,
                    has_accessible_name=has_name,
                ))

        return landmarks

    def _aria_attributes(self, soup: BeautifulSoup) -> dict:
        """Extract ARIA attributes from interactive elements."""
        aria_attrs = {
            "roles": [],
            "labels": [],
            "describedby": [],
            "live_regions": [],
            "expanded": [],
            "controls": [],
        }

        for elem in soup.find_all(True):  # All elements
            # role
            role = elem.get("role", "").strip()
            if role:
                aria_attrs["roles"].append({
                    "element": elem.name,
                    "role": role,
                    "id": elem.get("id", "").strip(),
                })

            # aria-label
            aria_label = elem.get("aria-label", "").strip()
            if aria_label:
                aria_attrs["labels"].append({
                    "element": elem.name,
                    "label": aria_label,
                    "id": elem.get("id", "").strip(),
                })

            # aria-labelledby
            aria_labelledby = elem.get("aria-labelledby", "").strip()
            if aria_labelledby:
                aria_attrs["labels"].append({
                    "element": elem.name,
                    "labelledby": aria_labelledby,
                    "id": elem.get("id", "").strip(),
                })

            # aria-describedby
            aria_describedby = elem.get("aria-describedby", "").strip()
            if aria_describedby:
                aria_attrs["describedby"].append({
                    "element": elem.name,
                    "describedby": aria_describedby,
                    "id": elem.get("id", "").strip(),
                })

            # aria-live
            aria_live = elem.get("aria-live", "").strip()
            if aria_live:
                aria_attrs["live_regions"].append({
                    "element": elem.name,
                    "live": aria_live,
                    "id": elem.get("id", "").strip(),
                })

            # aria-expanded
            aria_expanded = elem.get("aria-expanded", "").strip()
            if aria_expanded:
                aria_attrs["expanded"].append({
                    "element": elem.name,
                    "expanded": aria_expanded,
                    "id": elem.get("id", "").strip(),
                })

            # aria-controls
            aria_controls = elem.get("aria-controls", "").strip()
            if aria_controls:
                aria_attrs["controls"].append({
                    "element": elem.name,
                    "controls": aria_controls,
                    "id": elem.get("id", "").strip(),
                })

        return aria_attrs