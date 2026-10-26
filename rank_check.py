
# import os
# import asyncio
# from urllib.parse import urlparse

# import httpx
# from dotenv import load_dotenv

# load_dotenv()

# LOGIN = os.getenv("DATAFORSEO_LOGIN")
# PASSWORD = os.getenv("DATAFORSEO_PASSWORD")

# API_URL = (
#     "https://api.dataforseo.com/v3/"
#     "serp/google/organic/live/advanced"
# )


# def normalize_domain(domain: str) -> str:
#     domain = domain.strip()
#     if "://" not in domain:
#         domain = "https://" + domain

#     parsed = urlparse(domain)
#     host = (parsed.hostname or "").lower().rstrip(".")

#     if not host:
#         raise ValueError("Invalid domain")

#     return host.removeprefix("www.")


# async def check_rank(
#     keyword: str,
#     domain: str = "infomagine.in",
#     location: str = "India",
#     language: str = "English",
#     deep: bool = True,
# ):
#     if not LOGIN or not PASSWORD:
#         raise RuntimeError(
#             "DATAFORSEO_LOGIN or DATAFORSEO_PASSWORD "
#             "missing from .env"
#         )

#     target = normalize_domain(domain)
#     depth = 100 if deep else 10

#     task = {
#         "keyword": keyword,
#         "location_name": location,
#         "language_name": language,
#         "device": "desktop",
#         "depth": depth,
#     }

#     if deep:
#         task["stop_crawl_on_match"] = [
#             {
#                 "match_value": target,
#                 "match_type": "with_subdomains",
#             }
#         ]
#         task["find_targets_in"] = ["organic"]

#     async with httpx.AsyncClient(timeout=90) as client:
#         response = await client.post(
#             API_URL,
#             json=[task],
#             auth=(LOGIN, PASSWORD),
#         )
#         response.raise_for_status()
#         data = response.json()

#     tasks = data.get("tasks") or []

#     if not tasks:
#         print("No task returned by DataForSEO.")
#         return

#     api_task = tasks[0]

#     if api_task.get("status_code") != 20000:
#         raise RuntimeError(
#             f"DataForSEO error: "
#             f"{api_task.get('status_message')}"
#         )

#     results = api_task.get("result") or []
#     result = results[0] if results else {}
#     items = result.get("items") or []

#     matched = None

#     for item in items:
#         if item.get("type") != "organic":
#             continue

#         result_domain = (
#             item.get("domain")
#             or urlparse(item.get("url", "")).hostname
#             or ""
#         ).lower().rstrip(".").removeprefix("www.")

#         if (
#             result_domain == target
#             or result_domain.endswith("." + target)
#         ):
#             matched = item
#             break

#     print("\n========== SEO RANK REPORT ==========")
#     print(f"Keyword       : {keyword}")
#     print(f"Domain        : {target}")
#     print(f"Location      : {location}")
#     print(f"Search depth  : {depth}")
#     print(f"API cost      : {api_task.get('cost', 'N/A')}")

#     if matched:
#         print("Status        : FOUND")
#         print(
#             "Google rank  :",
#             matched.get("rank_absolute", "Not provided"),
#         )
#         print("Ranking URL   :", matched.get("url", "N/A"))
#     else:
#         print("Status        : NOT FOUND")
#         print(
#             f"Domain not found in the returned organic "
#             f"results up to the configured depth of {depth}."
#         )
#         print("Google rank   : Unknown")

#     print("=====================================\n")


# async def main():
#     domain = input(
#         "Domain [infomagine.in]: "
#     ).strip() or "infomagine.in"

#     keyword = input(
#         "Keyword to check: "
#     ).strip()

#     if not keyword:
#         print("Please enter a keyword.")
#         return

#     location = input(
#         "Location [India]: "
#     ).strip() or "India"

#     deep_input = input(
#         "Search up to 100 results? [Y/n]: "
#     ).strip().lower()

#     deep = deep_input not in {"n", "no"}

#     try:
#         await check_rank(
#             keyword=keyword,
#             domain=domain,
#             location=location,
#             deep=deep,
#         )
#     except httpx.HTTPStatusError as exc:
#         print(
#             f"HTTP error {exc.response.status_code}: "
#             f"{exc.response.text[:1000]}"
#         )
#     except httpx.HTTPError as exc:
#         print(f"Network error: {exc}")
#     except (RuntimeError, ValueError) as exc:
#         print(f"Error: {exc}")


# if __name__ == "__main__":
#     asyncio.run(main())


import os
import asyncio
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

LOGIN = os.getenv("DATAFORSEO_LOGIN")
PASSWORD = os.getenv("DATAFORSEO_PASSWORD")

API_URL = (
    "https://api.dataforseo.com/v3/"
    "serp/google/organic/live/advanced"
)

MAX_DEPTH = 700
BATCH_SIZE = 100


def normalize_domain(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = f"https://{value}"

    host = (urlparse(value).hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("Invalid domain")

    return host.removeprefix("www.")


def domain_matches(result_domain: str, target: str) -> bool:
    host = (result_domain or "").lower().rstrip(".")
    host = host.removeprefix("www.")
    return host == target or host.endswith("." + target)



async def check_exact_rank(
    keyword: str,
    domain: str = "infomagine.in",
    location: str = "India",
    language: str = "English",
):
    if not LOGIN or not PASSWORD:
        raise RuntimeError("DataForSEO credentials missing in .env")

    target = normalize_domain(domain)

    payload = [{
        "keyword": keyword,
        "location_name": location,
        "language_name": language,
        "device": "desktop",
        "depth": 200,
        "stop_crawl_on_match": [{
            "match_value": target,
            "match_type": "with_subdomains",
        }],
        "find_targets_in": ["organic"],
    }]

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            API_URL,
            json=payload,
            auth=(LOGIN, PASSWORD),
        )
        response.raise_for_status()
        body = response.json()

    tasks = body.get("tasks") or []
    if not tasks:
        raise RuntimeError("DataForSEO returned no tasks")

    task = tasks[0]
    if task.get("status_code") != 20000:
        raise RuntimeError(task.get("status_message", "API error"))

    result_list = task.get("result") or []
    result = result_list[0] if result_list else {}
    items = result.get("items") or []

    for item in items:
        if item.get("type") != "organic":
            continue

        item_domain = (
            item.get("domain")
            or urlparse(item.get("url", "")).hostname
            or ""
        )

        if domain_matches(item_domain, target):
            rank = item.get("rank_absolute")
            print(f"Domain: {target}")
            print(f"Keyword: {keyword}")
            print(f"Exact organic rank: {rank}")
            print(f"URL: {item.get('url')}")
            print(f"API cost: {task.get('cost', 'N/A')}")
            return {
                "found": True,
                "position": rank,
                "url": item.get("url"),
                "cost": task.get("cost"),
            }

    print(f"Domain not found within the returned results (depth 200).")
    print("Exact rank remains unknown.")
    return {
        "found": False,
        "position": None,
        "status": "not_found_within_limit",
        "max_depth": 200,
        "cost": task.get("cost"),
    }



async def main():
    domain = input("Domain [infomagine.in]: ").strip() or "infomagine.in"
    keyword = input("Keyword: ").strip()
    location = input("Location [India]: ").strip() or "India"

    if not keyword:
        print("A keyword is required.")
        return

    try:
        await check_exact_rank(keyword, domain, location)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

