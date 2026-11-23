from __future__ import annotations
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from app.modules.parser.models.eeat_data import EEATData, EEATSignal


class EEATAnalyzer:
    """
    Extracts observable E-E-A-T trust signals from HTML.
    
    Each signal returns EEATSignal with found/confidence/evidence/location
    for context-aware rule evaluation (YMYL vs non-YMYL).
    """
    
    # Keywords for link detection
    POLICY_KEYWORDS = {
        "privacy": ["privacy", "privacy-policy", "data-protection", "gdpr", "cookie-policy"],
        "terms": ["terms", "terms-of-service", "terms-of-use", "legal", "conditions"],
        "editorial": ["editorial", "editorial-policy", "content-policy", "guidelines", "standards"],
    }
    
    PAGE_KEYWORDS = {
        "about": ["about", "about-us", "our-story", "company", "team", "mission"],
        "contact": ["contact", "contact-us", "get-in-touch", "support", "help"],
    }
    
    AUTHOR_SELECTORS = [
        '[rel="author"]',
        '.author-name', '.byline', '.post-author', '.entry-author',
        '[itemprop="author"]', '[itemprop="name"]',
        '.author-bio', '.author-info', '.writer',
        'meta[name="author"]', 'meta[property="article:author"]',
    ]
    
    EXPERTISE_SELECTORS = [
        '[itemprop="jobTitle"]', '[itemprop="worksFor"]',
        '.author-title', '.author-role', '.credentials',
        '.author-description', '.bio', '.expertise',
    ]
    
    DATE_SELECTORS = [
        '[itemprop="datePublished"]', '[itemprop="dateModified"]',
        'meta[property="article:published_time"]',
        'meta[property="article:modified_time"]',
        'time[datetime]', '.published-date', '.post-date',
        '.entry-date', '.article-date', '.date',
    ]
    
    ADDRESS_SELECTORS = [
        '[itemprop="address"]', '.address', '.location',
        '.contact-address', '[itemprop="streetAddress"]',
        '.footer-address', '.company-address',
    ]
    
    TRUST_SIGNAL_SELECTORS = [
        '[itemprop="review"]', '[itemprop="rating"]', '[itemprop="aggregateRating"]',
        '.trust-badge', '.certification', '.badge', '.seal',
        '.testimonial', '.review', '.rating',
        '[class*="trust"]', '[class*="certif"]', '[class*="badge"]',
    ]
    
    DISCLAIMER_KEYWORDS = [
        "disclaimer", "not medical advice", "not financial advice",
        "not legal advice", "for informational purposes",
        "consult a professional", "past performance",
    ]
    
    AFFILIATE_KEYWORDS = [
        "affiliate", "affiliate link", "sponsored", "partner",
        "commission", "referral", "advertising disclosure",
    ]
    
    CITATION_SELECTORS = [
        'cite', 'blockquote cite', '[itemprop="citation"]',
        '.citation', '.reference', '.source',
        'a[href^="http"]:has(> cite)',  # links wrapping cite
    ]
    
    YMYL_KEYWORDS = {
        "financial": ["investment", "trading", "stock", "crypto", "mortgage", "loan", "credit", "banking", "insurance", "tax", "retirement", "pension", "financial advisor"],
        "health": ["medical", "health", "disease", "treatment", "symptom", "diagnosis", "medication", "drug", "therapy", "hospital", "doctor", "clinic", "wellness", "nutrition", "diet", "supplement", "fitness"],
        "safety": ["safety", "emergency", "first aid", "recall", "hazard", "toxic", "poison", "dangerous"],
        "legal": ["legal", "law", "attorney", "lawyer", "court", "lawsuit", "contract", "litigation"],
        "news": ["breaking news", "election", "vote", "government", "policy", "regulation"],
        "shopping": ["buy", "purchase", "order", "checkout", "cart", "price", "deal", "discount"],
    }

    def __init__(self):
        self._cache = {}

    def analyze(self, soup: BeautifulSoup, url: str = "", page_type: str = "") -> EEATData:
        """Main entry point — extracts all 14 signals."""
        base_url = self._get_base_url(url)
        
        return EEATData(
            privacy_policy=self._find_policy_link(soup, base_url, "privacy"),
            terms_of_service=self._find_policy_link(soup, base_url, "terms"),
            editorial_policy=self._find_policy_link(soup, base_url, "editorial"),
            author_byline=self._extract_author_byline(soup),
            author_expertise=self._extract_author_expertise(soup),
            content_dates=self._extract_dates(soup),
            physical_address=self._extract_address(soup),
            about_page=self._find_page_link(soup, base_url, "about"),
            contact_page=self._find_page_link(soup, base_url, "contact"),
            trust_signals=self._extract_trust_signals(soup),
            disclaimers=self._extract_disclaimers(soup),
            affiliate_disclosure=self._extract_affiliate_disclosure(soup),
            external_citations=self._extract_citations(soup),
            ymyl_topics=self._detect_ymyl(soup, page_type),
        )

    # --- Policy Links ---
    def _find_policy_link(self, soup: BeautifulSoup, base_url: str, policy_type: str) -> EEATSignal:
        keywords = self.POLICY_KEYWORDS.get(policy_type, [])
        
        # 1. Check <link rel="..."> in head
        for link in soup.find_all("link", rel=True):
            rel = link.get("rel", [])
            if isinstance(rel, str): rel = [rel]
            href = link.get("href", "").lower()
            if any(kw in " ".join(rel).lower() for kw in keywords) or any(kw in href for kw in keywords):
                return EEATSignal(True, 0.9, f"<link rel={rel} href={href}>", "head link")
        
        # 2. Check anchor links in body (footer, nav, header)
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").lower()
            text = anchor.get_text(" ", strip=True).lower()
            if any(kw in href for kw in keywords) or any(kw in text for kw in keywords):
                abs_url = urljoin(base_url, anchor["href"])
                return EEATSignal(found=True, confidence=0.8, evidence=f"Link: {text} -> {abs_url}", location=f"a[href={anchor['href']}]")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- Page Links (About, Contact) ---
    def _find_page_link(self, soup: BeautifulSoup, base_url: str, page_type: str) -> EEATSignal:
        keywords = self.PAGE_KEYWORDS.get(page_type, [])
        
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").lower()
            text = anchor.get_text(" ", strip=True).lower()
            if any(kw in href for kw in keywords) or any(kw in text for kw in keywords):
                abs_url = urljoin(base_url, anchor["href"])
                return EEATSignal(found=True, confidence=0.75, evidence=f"Link: {text} \u2192 {abs_url}", location=f"a[href={anchor['href']}]")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- Author ---
    def _extract_author_byline(self, soup: BeautifulSoup) -> EEATSignal:
        for selector in self.AUTHOR_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    # Handle meta tags
                    if el.name == "meta":
                        content = el.get("content", "").strip()
                        if content:
                            return EEATSignal(found=True, confidence=0.85, evidence=f"Meta author: {content}", location=selector)
                    else:
                        text = el.get_text(" ", strip=True)
                        if text and len(text) > 2:
                            return EEATSignal(found=True, confidence=0.8, evidence=f"Author: {text[:100]}", location=selector)
            except Exception:
                continue
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    def _extract_author_expertise(self, soup: BeautifulSoup) -> EEATSignal:
        # Look for expertise signals near author byline
        for selector in self.EXPERTISE_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    text = el.get_text(" ", strip=True)
                    if text and len(text) > 3:
                        return EEATSignal(found=True, confidence=0.7, evidence=f"Expertise: {text[:150]}", location=selector)
            except Exception:
                continue
        
        # Check for author bio sections
        bio_sections = soup.select('.author-bio, .author-info, .bio, [itemprop="description"]')
        for section in bio_sections:
            text = section.get_text(" ", strip=True)
            if text and len(text) > 50:  # Substantial bio
                return EEATSignal(found=True, confidence=0.6, evidence=f"Bio: {text[:200]}", location="author bio section")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- Dates ---
    def _extract_dates(self, soup: BeautifulSoup) -> EEATSignal:
        found_dates = []
        
        for selector in self.DATE_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    if el.name == "meta":
                        dt = el.get("content", "").strip()
                    elif el.name == "time":
                        dt = el.get("datetime", "").strip() or el.get_text(" ", strip=True)
                    else:
                        dt = el.get_text(" ", strip=True)
                    
                    if dt and self._looks_like_date(dt):
                        found_dates.append(dt)
            except Exception:
                continue
        
        if found_dates:
            return EEATSignal(found=True, confidence=0.8, evidence=f"Dates found: {', '.join(found_dates[:3])}", location="date selectors")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    def _looks_like_date(self, text: str) -> bool:
        # Simple date pattern detection
        patterns = [
            r"\d{4}-\d{2}-\d{2}",           # 2024-01-15
            r"\d{2}/\d{2}/\d{4}",           # 01/15/2024
            r"\d{1,2}\s+\w+\s+\d{4}",       # 15 January 2024
            r"\w+\s+\d{1,2},?\s+\d{4}",     # January 15, 2024
        ]
        return any(re.search(p, text) for p in patterns)

    # --- Address ---
    def _extract_address(self, soup: BeautifulSoup) -> EEATSignal:
        for selector in self.ADDRESS_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    text = el.get_text(" ", strip=True)
                    if text and len(text) > 10 and self._looks_like_address(text):
                        return EEATSignal(found=True, confidence=0.75, evidence=f"Address: {text[:200]}", location=selector)
            except Exception:
                continue
        
        # Check footer for address-like content
        footer = soup.find("footer") or soup.find(class_=re.compile("footer"))
        if footer:
            text = footer.get_text(" ", strip=True)
            if self._looks_like_address(text):
                return EEATSignal(found=True, confidence=0.5, evidence=f"Footer address: {text[:200]}", location="footer")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    def _looks_like_address(self, text: str) -> bool:
        # Heuristic: street number + street name + city/state/zip indicators
        has_number = bool(re.search(r"\d+", text))
        has_street = bool(re.search(r"\b(st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|ct|court|pl|place|pkwy|parkway)\b", text, re.I))
        has_city_state = bool(re.search(r"\b[A-Z]{2}\s+\d{5}", text))  # CA 90210
        return has_number and (has_street or has_city_state)

    # --- Trust Signals ---
    def _extract_trust_signals(self, soup: BeautifulSoup) -> EEATSignal:
        signals_found = []
        
        for selector in self.TRUST_SIGNAL_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    text = el.get_text(" ", strip=True)
                    alt = el.get("alt", "").strip()
                    title = el.get("title", "").strip()
                    class_names = " ".join(el.get("class", []))
                    
                    evidence = text or alt or title or class_names
                    if evidence and len(evidence) > 2:
                        signals_found.append(evidence[:100])
            except Exception:
                continue
        
        # Check for structured data reviews/ratings
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string or "{}")
                if isinstance(data, dict) and data.get("@type") in ["Review", "AggregateRating", "Product"]:
                    signals_found.append(f"Schema: {data.get('@type')}")
            except Exception:
                pass
        
        if signals_found:
            return EEATSignal(found=True, confidence=0.7, evidence=f"Trust signals: {'; '.join(signals_found[:5])}", location="trust selectors + schema")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- Disclaimers ---
    def _extract_disclaimers(self, soup: BeautifulSoup) -> EEATSignal:
        text_content = soup.get_text(" ", strip=True).lower()
        
        for kw in self.DISCLAIMER_KEYWORDS:
            if kw in text_content:
                # Find surrounding context
                idx = text_content.index(kw)
                context = text_content[max(0, idx-100):idx+200]
                return EEATSignal(found=True, confidence=0.8, evidence=f"Disclaimer: {context.strip()}", location="page text")
        
        # Check for explicit disclaimer elements
        disclaimer_els = soup.select('[class*="disclaimer"], [id*="disclaimer"], .legal-notice')
        for el in disclaimer_els:
            text = el.get_text(" ", strip=True)
            if text:
                return EEATSignal(found=True, confidence=0.9, evidence=f"Disclaimer element: {text[:200]}", location="disclaimer element")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- Affiliate Disclosure ---
    def _extract_affiliate_disclosure(self, soup: BeautifulSoup) -> EEATSignal:
        text_content = soup.get_text(" ", strip=True).lower()
        
        for kw in self.AFFILIATE_KEYWORDS:
            if kw in text_content:
                idx = text_content.index(kw)
                context = text_content[max(0, idx-100):idx+200]
                return EEATSignal(found=True, confidence=0.75, evidence=f"Affiliate disclosure: {context.strip()}", location="page text")
        
        # Check for explicit affiliate disclosure elements
        affiliate_els = soup.select('[class*="affiliate"], [class*="sponsored"], [class*="disclosure"]')
        for el in affiliate_els:
            text = el.get_text(" ", strip=True)
            if text and any(kw in text.lower() for kw in self.AFFILIATE_KEYWORDS):
                return EEATSignal(found=True, confidence=0.85, evidence=f"Affiliate element: {text[:200]}", location="affiliate element")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- Citations ---
    def _extract_citations(self, soup: BeautifulSoup) -> EEATSignal:
        citations = []
        
        for selector in self.CITATION_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    if el.name == "cite":
                        text = el.get_text(" ", strip=True)
                        if text:
                            citations.append(text[:100])
                    elif el.name == "a":
                        href = el.get("href", "")
                        text = el.get_text(" ", strip=True)
                        if href.startswith("http") and text:
                            citations.append(f"{text} \u2192 {href}")
                    elif el.name == "blockquote":
                        cite = el.get("cite", "")
                        text = el.get_text(" ", strip=True)
                        if cite or text:
                            citations.append(f"Blockquote: {text[:100]}")
            except Exception:
                continue
        
        # Check for reference lists
        ref_lists = soup.select('.references, .bibliography, .citation-list, [class*="reference"]')
        for ref_list in ref_lists:
            items = ref_list.find_all(["li", "p"])
            for item in items[:5]:
                text = item.get_text(" ", strip=True)
                if text:
                    citations.append(text[:100])
        
        if citations:
            return EEATSignal(found=True, confidence=0.7, evidence=f"Citations: {'; '.join(citations[:5])}", location="citation selectors")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    # --- YMYL Detection ---
    def _detect_ymyl(self, soup: BeautifulSoup, page_type: str) -> EEATSignal:
        text_content = soup.get_text(" ", strip=True).lower()
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(" ", strip=True).lower()
        
        h1_text = ""
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(" ", strip=True).lower()
        
        combined = f"{title} {h1_text} {text_content[:5000]}"
        detected_categories = []
        
        for category, keywords in self.YMYL_KEYWORDS.items():
            matches = [kw for kw in keywords if kw in combined]
            if matches:
                detected_categories.append(f"{category}: {', '.join(matches[:3])}")
        
        # Also check page_type hint
        if page_type in ("medical", "health", "finance", "legal", "news", "shopping", "ymyl"):
            detected_categories.append(f"page_type: {page_type}")
        
        if detected_categories:
            return EEATSignal(found=True, confidence=0.8, evidence=f"YMYL topics: {'; '.join(detected_categories)}", location="keyword detection")
        
        return EEATSignal(found=False, confidence=0.0, evidence="", location="")

    def _get_base_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return ""