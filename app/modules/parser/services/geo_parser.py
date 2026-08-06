"""Geo Parser - Extracts local SEO and geographic information."""
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import re


class GeoParser:
    """Extracts local SEO and geographic information."""
    
    # Common address patterns
    ADDRESS_PATTERNS = [
        r'\d+\s+[A-Za-z0-9\s,]+(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|court|ct|place|pl)\b',
        r'\d+\s+[A-Za-z0-9\s,]+(?:floor|suite|unit|apt|apartment)\s*[#]?\s*\d*',
        r'(?:P\.?O\.?\s*Box|Post\s*Office\s*Box)\s*\d+'
    ]
    
    # Phone number patterns
    PHONE_PATTERNS = [
        r'\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',  # US
        r'\+?[0-9]{1,3}[-.\s]?\(?[0-9]{2,4}\)?[-.\s]?[0-9\s]{6,12}'  # International
    ]
    
    # Business hours patterns
    HOURS_PATTERNS = [
        r'(?:monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)',
        r'\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)',
        r'(?:open|close|closed|hours)'
    ]
    
    @staticmethod
    def extract_address_info(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract address information from page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Address information
        """
        address_info = {
            "found": False,
            "structured_data": {},
            "text_matches": []
        }
        
        # Check for structured data (schema.org address)
        address_schema = GeoParser._find_schema_address(soup)
        if address_schema:
            address_info["found"] = True
            address_info["structured_data"] = address_schema
            return address_info
        
        # Search in page text
        text = GeoParser._get_page_text(soup)
        
        for pattern in GeoParser.ADDRESS_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                address_info["found"] = True
                address_info["text_matches"].extend(matches[:3])  # Limit to 3
                break
        
        return address_info
    
    @staticmethod
    def extract_phone_numbers(soup: BeautifulSoup) -> List[str]:
        """
        Extract phone numbers from page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of phone numbers found
        """
        phone_numbers = []
        text = GeoParser._get_page_text(soup)
        
        for pattern in GeoParser.PHONE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                # Normalize phone number
                normalized = GeoParser._normalize_phone(match)
                # Filter out invalid numbers (too long - likely social media IDs)
                if normalized and normalized not in phone_numbers:
                    # Remove leading + or 1, check digit count
                    digits_only = re.sub(r'[^\d]', '', normalized)
                    # Valid phone numbers are typically 10-15 digits
                    if 10 <= len(digits_only) <= 15:
                        phone_numbers.append(normalized)
        
        return phone_numbers
    
    @staticmethod
    def extract_business_hours(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract business hours information.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Business hours information
        """
        hours_info = {
            "found": False,
            "structured_data": {},
            "text_matches": []
        }
        
        # Check for schema.org openingHours
        schema_hours = GeoParser._find_schema_hours(soup)
        if schema_hours:
            hours_info["found"] = True
            hours_info["structured_data"] = schema_hours
            return hours_info
        
        # Search in page text - require day name AND time pattern together
        text = GeoParser._get_page_text(soup)
        
        # More strict pattern: day name followed by time within reasonable distance
        strict_hours_pattern = r'(?:monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)[^\n]{0,50}?\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)'
        matches = re.findall(strict_hours_pattern, text, re.IGNORECASE)
        
        if matches:
            hours_info["found"] = True
            for match in matches[:3]:
                context = match.strip()
                if context not in hours_info["text_matches"]:
                    hours_info["text_matches"].append(context)
        
        return hours_info
    
    @staticmethod
    def extract_geo_meta_tags(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract geo-related meta tags.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Geo meta tag information
        """
        geo_info = {
            "found": False,
            "latitude": "",
            "longitude": "",
            "geo_position": "",
            "geo_region": "",
            "geo_placename": ""
        }
        
        # Check for geo meta tags
        geo_position = soup.find('meta', attrs={'name': 'geo.position'})
        if geo_position:
            geo_info["found"] = True
            geo_info["geo_position"] = geo_position.get('content', '').strip()
            # Parse latitude and longitude
            if geo_info["geo_position"]:
                parts = geo_info["geo_position"].split(';')
                if len(parts) == 2:
                    try:
                        geo_info["latitude"] = float(parts[0].strip())
                        geo_info["longitude"] = float(parts[1].strip())
                    except ValueError:
                        pass
        
        geo_region = soup.find('meta', attrs={'name': 'geo.region'})
        if geo_region:
            geo_info["geo_region"] = geo_region.get('content', '').strip()
        
        geo_placename = soup.find('meta', attrs={'name': 'geo.placename'})
        if geo_placename:
            geo_info["geo_placename"] = geo_placename.get('content', '').strip()
        
        return geo_info
    
    @staticmethod
    def extract_location_keywords(soup: BeautifulSoup) -> List[str]:
        """
        Extract location-related keywords from content.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of location keywords
        """
        location_keywords = []
        text = GeoParser._get_page_text(soup).lower()
        
        # Common location indicators
        location_indicators = [
            'city', 'town', 'village', 'county', 'state', 'province', 'country',
            'near', 'located', 'address', 'directions', 'map', 'location'
        ]
        
        # Extract sentences containing location indicators
        sentences = re.split(r'[.!?]', text)
        for sentence in sentences:
            if any(indicator in sentence for indicator in location_indicators):
                # Extract potential location names (capitalized words)
                words = sentence.split()
                for word in words:
                    if word[0].isupper() and len(word) > 3 and word not in location_keywords:
                        location_keywords.append(word)
        
        return location_keywords[:10]  # Limit to 10
    
    @staticmethod
    def check_google_my_business(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Check for Google My Business integration.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            GMB integration analysis
        """
        gmb_indicators = {
            "found": False,
            "integration_score": 0,
            "indicators": []
        }
        
        # Check for Google Maps embed
        maps_embeds = soup.find_all('iframe', src=re.compile(r'maps\.google|google\.com/maps'))
        if maps_embeds:
            gmb_indicators["found"] = True
            gmb_indicators["integration_score"] += 1
            gmb_indicators["indicators"].append("Google Maps embed")
        
        # Check for Google Maps links
        maps_links = soup.find_all('a', href=re.compile(r'maps\.google|google\.com/maps'))
        if maps_links:
            gmb_indicators["found"] = True
            gmb_indicators["integration_score"] += 1
            gmb_indicators["indicators"].append("Google Maps link")
        
        # Check for Google Business Profile schema
        business_schema = soup.find_all('script', type='application/ld+json')
        for script in business_schema:
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    schema_type = data.get('@type', '')
                    if 'LocalBusiness' in str(schema_type) or 'Organization' in str(schema_type):
                        gmb_indicators["found"] = True
                        gmb_indicators["integration_score"] += 1
                        gmb_indicators["indicators"].append("Local Business Schema")
                        break
            except:
                continue
        
        return gmb_indicators
    
    @staticmethod
    def check_nap_consistency(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Check NAP (Name, Address, Phone) consistency.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            NAP consistency analysis
        """
        nap_info = {
            "consistency_score": 0.0,
            "name_found": False,
            "address_found": False,
            "phone_found": False,
            "instances": {
                "name": [],
                "address": [],
                "phone": []
            }
        }
        
        # Extract NAP elements
        # This is a simplified check - full NAP consistency would require
        # comparing across multiple pages
        
        text = GeoParser._get_page_text(soup)
        
        # Check for phone numbers
        phones = GeoParser.extract_phone_numbers(soup)
        if phones:
            nap_info["phone_found"] = True
            nap_info["instances"]["phone"] = phones
        
        # Check for address
        address = GeoParser.extract_address_info(soup)
        if address.get("found"):
            nap_info["address_found"] = True
            nap_info["instances"]["address"] = address.get("text_matches", [])
        
        # Calculate consistency score
        found_count = sum([
            nap_info["name_found"],
            nap_info["address_found"],
            nap_info["phone_found"]
        ])
        nap_info["consistency_score"] = found_count / 3.0
        
        return nap_info
    
    @staticmethod
    def _find_schema_address(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Find address in schema.org markup."""
        import json
        
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                # Search for address in schema
                address_data = GeoParser._search_for_address(data)
                if address_data:
                    return address_data
            except:
                continue
        return None
    
    @staticmethod
    def _search_for_address(data: any) -> Optional[Dict[str, Any]]:
        """Recursively search for address in schema data."""
        if isinstance(data, dict):
            if 'address' in data:
                return {"type": data.get('@type', ''), "address": data['address']}
            for value in data.values():
                result = GeoParser._search_for_address(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = GeoParser._search_for_address(item)
                if result:
                    return result
        return None
    
    @staticmethod
    def _find_schema_hours(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Find business hours in schema.org markup."""
        import json
        
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                hours_data = GeoParser._search_for_hours(data)
                if hours_data:
                    return hours_data
            except:
                continue
        return None
    
    @staticmethod
    def _search_for_hours(data: any) -> Optional[Dict[str, Any]]:
        """Recursively search for opening hours in schema data."""
        if isinstance(data, dict):
            if 'openingHours' in data or 'openingHoursSpecification' in data:
                return {
                    "opening_hours": data.get('openingHours', []),
                    "hours_specification": data.get('openingHoursSpecification', [])
                }
            for value in data.values():
                result = GeoParser._search_for_hours(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = GeoParser._search_for_hours(item)
                if result:
                    return result
        return None
    
    @staticmethod
    def _get_page_text(soup: BeautifulSoup) -> str:
        """Get clean text from page."""
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
        return soup.get_text(separator=' ', strip=True)
    
    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number format."""
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)
        # Remove leading zeros or country code duplicates
        if cleaned.startswith('+'):
            return '+' + re.sub(r'^\+0+', '', cleaned)
        return cleaned