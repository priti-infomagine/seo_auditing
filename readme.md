# SEO Auditing Backend

FastAPI backend for crawling websites, parsing pages, evaluating SEO rules,
calculating scores, running Google PageSpeed/Lighthouse checks, and generating
reports. Long-running work is handled by Celery workers through Redis.

## Technology Stack

- Python 3.11
- FastAPI and Uvicorn
- PostgreSQL with async SQLAlchemy and Alembic
- Redis as the Celery broker and result backend
- Celery for crawling, audit analysis, reports, authentication cleanup, and Lighthouse tasks
- Playwright for browser-based crawling and rendering checks
- LangChain/LangGraph/Ollama for chat and LLM features
- Pytest and pytest-asyncio for tests

## Architecture

The application starts at `app.main:app`. The routing hierarchy is:

```text
app.main:app
`-- /api/v1
    |-- /auth
    |-- /health
    |-- /crawler
    |-- /audit and /audits
    |-- /parser
    |-- /scorer
    |-- /config/ignore-patterns
    |-- /chat
    |-- /reports
    |-- /plans
    `-- /lighthouse
```

The main audit pipeline is asynchronous:

```text
POST /api/v1/audit/analyze
  -> crawler.crawl_website (crawler queue)
  -> audit.run_analysis_pipeline (audit queue)
  -> parse pages -> evaluate rules -> calculate SEO scores -> reports
```

Lighthouse checks create a tracking `CrawlJob`, enqueue `lighthouse.run_check`
on the `crawler` queue, and expose separate status and result endpoints.

## Project Structure

```text
.
|-- app/
|   |-- main.py                    # FastAPI app, lifecycle, health endpoints
|   |-- api/
|   |   `-- endpoints/v1/          # Versioned HTTP routers
|   |-- core/
|   |   |-- config.py              # Pydantic settings loaded from .env
|   |   |-- database.py            # Async SQLAlchemy engine and sessions
|   |   |-- datetime_utils.py
|   |   |-- logger.py
|   |   `-- security.py
|   |-- modules/
|   |   |-- audit/                 # Audit pipeline, models, repositories, tasks
|   |   |-- auth/                  # Users, OTP, tokens, authentication tasks
|   |   |-- chat/                  # Audit chat and retrieval/tool support
|   |   |-- config/                # Ignore-pattern configuration
|   |   |-- crawler/               # Crawling, fetching, extraction, persistence
|   |   |-- llm/                   # LLM integration and configuration
|   |   |-- parser/                # Page parsing, analyzers, extractors
|   |   |-- payment/               # Plans and subscriptions
|   |   |-- reports/               # PDF generation, storage, email delivery
|   |   |-- rule_engine/           # SEO rules and issue evaluation
|   |   |-- scorer/                # SEO score and report assembly
|   |   `-- seprate_checks/        # Additional checks (currently Lighthouse)
|   |-- shared/
|   |   |-- tasks/                 # Celery app, queues, worker DB helpers
|   |   |-- services/              # Shared services such as email
|   |   |-- constants/
|   |   |-- exceptions/
|   |   |-- utils/
|   |   `-- validators/
|   `-- tests/                     # Application and API tests
|-- alembic/
|   |-- env.py                     # Migration environment and model imports
|   `-- versions/                  # Database migration revisions
|-- scripts/
|   |-- start_worker.ps1           # Windows Celery worker launcher
|   `-- start_worker.sh            # Linux/macOS Celery worker launcher
|-- monitoring/prometheus/         # Prometheus configuration
|-- output/                        # Generated audit/report output
|-- logs/                          # Runtime logs
|-- agent/                         # Standalone agent experiments/utilities
|-- Dockerfile                     # Python 3.11 API image
|-- docker-compose.yml             # Redis service and persistent volume
|-- requirements.txt               # Pinned Python dependencies
|-- alembic.ini                    # Alembic configuration
|-- pytest.ini                     # Pytest discovery and asyncio settings
|-- pyrightconfig.json             # Pylance/Pyright settings
`-- *.py                           # Diagnostic, migration, and CLI utilities
```

The directory name `seprate_checks` is misspelled in the current codebase and
is part of the import path; do not rename it without updating imports.

## Prerequisites

- Python 3.11
- PostgreSQL 14+ (database: `seo_audit` by default)
- Redis 7+
- Git
- Playwright browser binaries for browser-based crawler tests

PostgreSQL and Redis are expected at `localhost` with the default settings.
The current `docker-compose.yml` starts **Redis only**; it does not start the
API, PostgreSQL, Celery worker, Celery beat, or MinIO.

## Local Setup

### Windows PowerShell

```powershell
git clone <repository-url>
Set-Location seo_auditing

py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install
```

### Linux/macOS

```bash
git clone <repository-url>
cd seo_auditing
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install
```

Create a `.env` file in the repository root. The defaults in
`app/core/config.py` are suitable only for local development:

```dotenv
APP_NAME=Automated SEO & Website Audit Tool
DEBUG=false
SECRET_KEY=replace-this-value
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/seo_audit
DATABASE_SYNC_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/seo_audit
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_BROKER_URL=redis://127.0.0.1:6379/0
REDIS_BACKEND_URL=redis://127.0.0.1:6379/1
GOOGLE_PAGESPEED_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
```

Set SMTP values when email delivery is required. Set `CHAT_AUTH_ENABLED` and
the relevant LLM credentials when protected chat or external LLM features are
enabled. Never commit real credentials or the local `.env` file.

## Start Dependencies

Start PostgreSQL separately, create the database, and start Redis. Redis can
be started with Docker from the repository root:

```bash
docker compose up -d redis
```

Or run Redis locally:

```bash
redis-server
redis-cli ping
# Expected: PONG
```

## Database Migrations

The API calls `Base.metadata.create_all` during startup for development. Use
Alembic for controlled schema changes and deployments:

```bash
alembic upgrade head
alembic current
alembic history
```

To create a migration after changing registered models:

```bash
alembic revision --autogenerate -m "describe the schema change"
```

Alembic reads `DATABASE_SYNC_URL` when it is set; otherwise it converts the
async driver in `DATABASE_URL` to `psycopg2`.

## Run the Application

Start the API in one terminal:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Start a worker in a second terminal. The worker must consume both `crawler`
and `audit` queues for the full audit pipeline:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_worker.ps1
```

```bash
./scripts/start_worker.sh
```

To consume email tasks as well:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_worker.ps1 -Queues "crawler,audit,email"
```

Start Celery Beat separately when scheduled cleanup tasks are needed:

```bash
python -m celery --app=app.shared.tasks.celery_app beat --loglevel=info
```

The Dockerfile builds the API image only. It does not configure PostgreSQL,
Redis, workers, or Beat, so those services must still be supplied separately.

## API and Health Checks

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Basic health: <http://localhost:8000/health>
- Detailed dependencies: <http://localhost:8000/health/detailed>
- API base path: <http://localhost:8000/api/v1>

The detailed health endpoint checks PostgreSQL, Redis, and Celery. A status of
`no_workers` for Celery means the API is reachable but no worker responded.

### Sitemap Check API

The sitemap checker uses a lightweight summary response and paginated follow-up
endpoints. This prevents Swagger and frontend clients from loading every URL
and raw XML document at once:

```text
POST /api/v1/sitemap/check
GET  /api/v1/sitemap/{check_id}/files?page=1&page_size=20
GET  /api/v1/sitemap/{check_id}/files/{file_index}/urls?page=1&page_size=100
GET  /api/v1/sitemap/{check_id}/files/{file_index}/raw
```

The POST response contains the check ID, summary, robots.txt evidence, and
recommendations. File metadata, URL lists, and raw XML are loaded separately.
Run `alembic upgrade head` before using this API on a new database.

## Tests

Run the normal test suite:

```bash
python -m pytest -v
```

Run a focused test file or module:

```bash
python -m pytest app/modules/parser/tests -v
python -m pytest app/modules/crawler/tests -v
```

Some tests perform live network crawling or require a real Redis/Celery
worker. Enable those explicitly with the flags used by the tests, for example:

```powershell
$env:RUN_LIVE_CRAWL="1"
python -m pytest app/modules/crawler/tests/integration/test_full_crawler.py -v -s
```

The repository uses `pytest.ini` with automatic asyncio support and discovers
Python test files broadly (`python_files = *.py`).

## Useful Utilities

```bash
python chat_cli.py
python diagnose_pipeline.py
python diagnose_gap.py
python verify_migration.py
python check_files.py
```

These scripts are diagnostics and developer utilities; inspect their source
before using them against a production database or website.

## Troubleshooting

- **Database connection errors:** verify PostgreSQL is running, the `seo_audit`
  database exists, and `DATABASE_URL` matches the local credentials.
- **Celery tasks remain queued:** verify Redis is reachable and start the
  worker with both `crawler,audit` queues. The full audit pipeline uses both.
- **First request is slow:** the API pre-warms the Celery producer at startup;
  a missing or slow Redis service can still delay the first task submission.
- **Browser launch errors:** run `playwright install` after installing Python
  dependencies.
- **Windows async subprocess errors:** use the provided PowerShell worker
  script and run the API with the project Python 3.11 environment.
- **Lighthouse results are unavailable:** set `GOOGLE_PAGESPEED_API_KEY` and
  ensure the Lighthouse worker is consuming the `crawler` queue.

## Production Notes

Replace the development `SECRET_KEY`, use HTTPS with `COOKIE_SECURE=true`,
provide managed PostgreSQL and Redis, run Alembic migrations before starting
the API, and keep credentials outside source control. Tune Celery pool and
concurrency settings for the deployment environment rather than copying the
Windows `solo` worker defaults unchanged.