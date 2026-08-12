import asyncio
from app.services.crawler.crawler import WebCrawler


async def main():
    # Debug: verify loop type
    loop = asyncio.get_running_loop()
    print(f"Running loop class: {loop.__class__.__name__}")
    
    crawler = WebCrawler()
    result = await crawler.crawl("https://www.reddit.com/")
    print(f"Final URL: {result.final_url}")
    print(f"Status: {result.http.get('status_code')}")
    print(f"Response time: {result.http.get('response_time')}s")


if __name__ == "__main__":
    asyncio.run(main())