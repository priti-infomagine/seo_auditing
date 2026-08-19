import asyncio
import sys

from playwright.async_api import async_playwright


async def main():
    loop = asyncio.get_running_loop()

    print("=" * 60)
    print("PLAYWRIGHT STANDALONE TEST")
    print("Platform:", sys.platform)
    print("Policy:", type(asyncio.get_event_loop_policy()).__name__)
    print("Loop:", type(loop).__name__)
    print("=" * 60)

    async with async_playwright() as p:
        print("Playwright started")

        browser = await p.chromium.launch(headless=True)

        print("Chromium started")

        page = await browser.new_page()
        await page.goto("https://example.com")

        print("Title:", await page.title())

        await browser.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsProactorEventLoopPolicy()
        )

    asyncio.run(main())