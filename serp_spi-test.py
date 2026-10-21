import httpx
from app.core.config import settings

login = settings.DATAFORSEO_LOGIN
password = settings.DATAFORSEO_PASSWORD

url = (
    "https://api.dataforseo.com/"
    "v3/serp/google/organic/live/advanced"
)

payload = [
    {
        "keyword": "web development",
        "location_name": "United States",
        "language_name": "English",
        "device": "mobile",
        "depth": 10,
    }
]

response = httpx.post(
    url,
    auth=(login, password),
    json=payload,
    timeout=60.0,
)

print("HTTP status:", response.status_code)
print("Response body:", response.text)
response.raise_for_status()
result = response.json()
print(result)
