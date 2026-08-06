# Crawler Test Module

A modular, pure crawler implementation for testing purposes.

## Architecture

The crawler is built with strict separation of concerns:

### Utils (`utils/`)
Pure utility functions with no business logic:
- `http_client.py` - HTTP request handling
- `url_utils.py` - URL normalization and validation
- `checksum.py` - Content checksum generation
- `mime_detector.py` - MIME type detection
- `html_compressor.py` - HTML compression

### Extractors (`extractors/`)
Parse raw content and return structured objects only:
- `link_extractor.py` - Extract links from HTML
- `asset_extractor.py` - Extract assets (images, CSS, JS, etc.)
- `metadata_extractor.py` - Extract response metadata
- `redirect_extractor.py` - Extract redirect chains

### Repositories (`repositories/`)
Database operations only:
- `crawl_job_repository.py` - CrawlJob CRUD
- `crawl_config_repository.py` - CrawlConfig CRUD
- `crawl_page_repository.py` - CrawlPage CRUD
- `page_link_repository.py` - PageLink CRUD
- `page_asset_repository.py` - PageAsset CRUD
- `page_snapshot_repository.py` - Snapshot storage
- `crawl_error_repository.py` - CrawlError CRUD
- `crawl_statistics_repository.py` - Statistics queries

### Services (`services/`)
Business logic + validation + persistence coordination:
- `fetch_service.py` - HTTP requests (Fetcher)
- `response_service.py` - Converts raw HTTP response to structured object
- `page_service.py` - Create/update CrawlPage
- `snapshot_service.py` - Store HTML snapshots
- `link_service.py` - Validate & persist links
- `asset_service.py` - Validate & persist assets
- `redirect_service.py` - Store redirect chains
- `crawl_error_service.py` - Error handling & retries
- `crawl_statistics_service.py` - Crawl summary
- `checksum_service.py` - Generate page checksum
- `crawl_config_service.py` - Manage crawl settings
- `crawl_queue_service.py` - Queue management (BFS/DFS, retries)
- `crawl_orchestrator.py` - Controls entire crawl lifecycle

## Data Flow

```
Fetcher → Downloads data
    ↓
Response Service → Converts raw HTTP response into structured response object
    ↓
Extractors → Parse raw content and return structured objects only
    ↓
Services → Business logic + validation + persistence
    ↓
Repositories → Database operations only
```

## Usage

```python
from crawler_test.services.crawl_orchestrator import CrawlOrchestrator

# Initialize orchestrator with database session and crawl job ID
orchestrator = CrawlOrchestrator(db, crawl_job_id)

# Crawl a page
await orchestrator.crawl_page("https://example.com", depth=0)

# Get summary
summary = await orchestrator.get_summary()
```

## Installation

```bash
pip install -r crawler_test/requirements.txt