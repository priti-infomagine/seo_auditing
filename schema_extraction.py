import json
import requests
import extruct
from w3lib.html import get_base_url

def extract_schema_from_url(url):
    # Set headers to mimic a browser request to avoid bot blocking
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Fetch the HTML content
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Calculate the base URL for relative schemas (e.g., links inside images/author profiles)
        base_url = get_base_url(response.text, response.url)
        
        # Extract all structured data types (JSON-LD, Microdata, Open Graph, etc.)
        schema_data = extruct.extract(response.text, base_url=base_url)
        
        return schema_data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return None

# --- Quick Test Run ---
target_url = "https://youtube.com"  # Replace with any website
extracted_data = extract_schema_from_url(target_url)

if extracted_data:
    # Print it out cleanly as a JSON object
    print(json.dumps(extracted_data, indent=2))
