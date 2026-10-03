import httpx
import base64
import os
import load_dotenv

load_dotenv()

login= os.getenv("DATAFORSEO_LOGIN")
password= os.getenv("DATAFORSEO_PASSWORD")
domain="https://infomagine.in/"

class DataForSEOClient:

    BASE_URL = "https://api.dataforseo.com/v3"

    def __init__(self, login: str, password: str):
        credentials = f"{login}:{password}".encode()
        encoded = base64.b64encode(credentials).decode()

        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    async def get_backlink_summary(self, domain: str):
        payload = [
            {
                "target": domain,
                "include_subdomains": True,
                "exclude_internal_backlinks": True,
                "backlinks_status_type": "live",
            }
        ]

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.BASE_URL}/backlinks/summary/live",
                headers=self.headers,
                json=payload,
            )

            response.raise_for_status()
            return response.json()

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
    ):
        payload = [
            {
                "target": domain,
                "limit": limit,
                "mode": "as_is",
            }
        ]

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.BASE_URL}/backlinks/backlinks/live",
                headers=self.headers,
                json=payload,
            )

            response.raise_for_status()
            return response.json()