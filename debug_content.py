"""Quick debug script to test content pipeline inline."""
import asyncio
from app.modules.category_check.core_seo.pipeline import CoreSEOCrawlerService
from app.modules.category_check.core_seo.models import CrawlResult

class MockCrawler:
    async def crawl(self, url):
        html = (
            "<html><head><title>Test Page</title>"
            '<meta name="description" content="A test page description here for testing purposes. This is a longer description to meet length requirements.">'
            '</head><body>'
            '<h1>Test Heading</h1>'
            '<p>This is a test paragraph with sufficient content to pass the word count threshold for content analysis. '
            'We need at least 300 words. Adding more text to ensure the word count is high enough for the content word count rule to pass during testing.</p>'
            '<p>Another paragraph of content for testing. We need enough text to make the word count pass the minimum threshold for content analysis rules.</p>'
            '<p>More paragraphs to add word count. Content depth is important for SEO. '
            'Search engines favor pages with substantial unique content that provides value to users. '
            'By providing comprehensive well-structured content websites can improve their visibility.</p>'
            '<p>Using short simple sentences helps users read fast. This page has easy text for testing.</p>'
            '</body></html>'
        )
        return CrawlResult(
            url=url,
            html=html,
            status_code=200,
            headers={'content-type': 'text/html; charset=utf-8'},
            success=True,
            final_url=url,
            response_time_ms=100,
        )

from app.modules.category_check.content.tests.test_pipeline import MockPageDiscoverer

async def main():
    service = CoreSEOCrawlerService()
    service.crawler = MockCrawler()
    service.page_discoverer = MockPageDiscoverer()
    
    print(f"run_content={service.run_content}")
    print(f"content_service={service.content_service}")
    
    audit_id = await service.start_audit(
        'https://example.com',
        max_pages=1, max_depth=1,
        audit_id='test-debug-123',
    )
    print(f"audit_id={audit_id}")
    
    import redis
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
    
    # Check content counters
    counters = r.hgetall(f'content:audit:{audit_id}:counters')
    print(f'Content counters: {counters}')
    
    # Check content state
    state = r.hgetall(f'content:audit:{audit_id}:state')
    print(f'Content state: {state}')
    
    # Check content stream length
    stream_len = r.xlen(f'content:events:{audit_id}')
    print(f'Content stream length: {stream_len}')
    
    # List recent events
    events = r.xrange(f'content:events:{audit_id}', count=30)
    for eid, fields in events:
        event_str = fields.get('event', '')
        if event_str:
            import json
            try:
                evt = json.loads(event_str)
                print(f'  {eid}: {evt["event_type"]} | data={evt.get("data", {}).get("url", evt.get("data", {}).get("rule_id", ""))}')
            except:
                print(f'  {eid}: raw event')
    
    # Check core_seo counters
    core_counters = r.hgetall(f'core_seo:audit:{audit_id}:counters')
    print(f'Core SEO counters: {core_counters}')
    
    # Clean up
    from app.modules.category_check.content.events import ContentEventBus
    from app.modules.category_check.core_seo.events import EventBus
    ContentEventBus.clear_audit_state(audit_id)
    EventBus.clear_audit_state(audit_id)

asyncio.run(main())
