"""
Backward compatibility: GeoParser → kept as legacy standalone utility.
Not integrated into ParserOrchestrator pipeline.
"""
from bs4 import BeautifulSoup


class GeoParser:
    """Legacy local SEO extractor."""

    @staticmethod
    def extract_address_info(soup: BeautifulSoup) -> dict:
        return {"found": False, "structured_data": {}, "text_matches": []}

    @staticmethod
    def extract_phone_numbers(soup: BeautifulSoup) -> list:
        return []

    @staticmethod
    def extract_business_hours(soup: BeautifulSoup) -> dict:
        return {"found": False, "structured_data": {}, "text_matches": []}

    @staticmethod
    def extract_geo_meta_tags(soup: BeautifulSoup) -> dict:
        return {
            "found": False,
            "latitude": "",
            "longitude": "",
            "geo_position": "",
            "geo_region": "",
            "geo_placename": "",
        }

    @staticmethod
    def extract_location_keywords(soup: BeautifulSoup) -> list:
        return []

    @staticmethod
    def check_google_my_business(soup: BeautifulSoup) -> dict:
        return {"found": False, "integration_score": 0, "indicators": []}

    @staticmethod
    def check_nap_consistency(soup: BeautifulSoup) -> dict:
        return {
            "consistency_score": 0.0,
            "name_found": False,
            "address_found": False,
            "phone_found": False,
            "instances": {"name": [], "address": [], "phone": []},
        }


__all__ = ["GeoParser"]
