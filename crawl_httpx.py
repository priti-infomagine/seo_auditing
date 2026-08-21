import asyncio
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup


# START_URL = "https://kanhahometutions.com"
START_URL = "https://infomagine.in"

MAX_CONCURRENT = 20
TIMEOUT = 20


def normalize_url(url):
    url = urldefrag(url)[0]

    parsed = urlparse(url)

    # Only HTTP/HTTPS
    if parsed.scheme not in ("http", "https"):
        return None

    # Remove fragment and trailing slash
    path = parsed.path.rstrip("/") or "/"

    # Ignore query strings for now.
    # Remove this if ?page=1, ?page=2 etc. are separate pages.
    return parsed._replace(
        path=path,
        query=""
    ).geturl()


def same_domain(url, base_domain):
    return urlparse(url).netloc == base_domain


def get_links(html, current_url, base_domain):
    soup = BeautifulSoup(html, "html.parser")

    links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        if not href:
            continue

        # Ignore these
        if href.startswith((
            "javascript:",
            "mailto:",
            "tel:",
            "data:"
        )):
            continue

        url = urljoin(current_url, href)
        url = normalize_url(url)

        if not url:
            continue

        if same_domain(url, base_domain):
            links.add(url)

    return links


async def crawl(start_url):
    start_url = normalize_url(start_url)

    base_domain = urlparse(start_url).netloc

    queue = deque([start_url])
    visited = set()

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140 Safari/537.36"
            )
        },
    ) as client:

        while queue:

            # Get a batch
            batch = []

            while queue and len(batch) < MAX_CONCURRENT:
                url = queue.popleft()

                if url in visited:
                    continue

                visited.add(url)
                batch.append(url)

            if not batch:
                continue

            print(f"\nFetching {len(batch)} URLs...")

            async def fetch(url):
                try:
                    response = await client.get(url)

                    return (
                        url,
                        response.status_code,
                        response.headers.get("content-type", ""),
                        response.text
                        if "text/html" in response.headers.get(
                            "content-type", ""
                        ).lower()
                        else ""
                    )

                except Exception as e:
                    return url, None, "", str(e)

            responses = await asyncio.gather(
                *(fetch(url) for url in batch)
            )

            for url, status, content_type, html in responses:

                print(f"[{status}] {url}")

                if status != 200:
                    continue

                if "text/html" not in content_type.lower():
                    continue

                links = get_links(
                    html,
                    url,
                    base_domain
                )

                print(f"    Found {len(links)} links")

                for link in links:

                    if link not in visited:
                        queue.append(link)

                        print(f"    + {link}")

            print(
                f"Queue: {len(queue)} | "
                f"Visited: {len(visited)}"
            )

    return visited


async def main():

    pages = await crawl(START_URL)

    print("\n" + "=" * 60)
    print(f"TOTAL PAGES CRAWLED: {len(pages)}")
    print("=" * 60)

    for page in sorted(pages):
        print(page)


if __name__ == "__main__":
    asyncio.run(main())