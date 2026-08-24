import httpx

url = "https://infomagine.in/"

response = httpx.get(
    url,
    follow_redirects=True,
    timeout=60,
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        )
    },
)

print("Status:", response.status_code)
print("Final URL:", response.url)
print("Content-Type:", response.headers.get("content-type"))
print("HTML length:", len(response.text))

print("\nFIRST 5000 CHARACTERS:")
print(response.text[:5000])

with open("debug.html", "w", encoding="utf-8") as f:
    f.write(response.text)

print("\nSaved response to debug.html")