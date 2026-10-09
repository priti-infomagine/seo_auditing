# Streaming Page-Level Audit

This module is an experimental, isolated alternative to the existing production audit pipeline.

## Goals

- Process each discovered page as an independent unit.
- Queue newly discovered pages immediately instead of waiting for the full crawl to finish.
- Keep the production audit path completely untouched.
- Reuse existing crawler, parser, rule engine, and scorer services where safe.

## Architecture

1. Seed URL enters the streaming audit API.
2. The audit record is created with a dedicated queue and namespace.
3. A page task executes one page lifecycle: fetch -> parse -> evaluate -> score -> persist.
4. New links are discovered from the page and scheduled only if they are new and within limits.
5. Aggregation combines page-level results into audit-level summary state.

## Redis namespace

The new architecture uses the `streaming_audit:{audit_id}:*` namespace to avoid colliding with existing audit keys.

## Database model

Two tables are intentionally kept minimal:

- `streaming_audit_runs`
- `streaming_page_results`

These store audit metadata and page-level JSON payloads without creating rule-specific or stage-specific tables.

## Scheduling model

The scheduler enforces:

- bounded concurrency
- max depth checks
- max page cap
- deduplication before scheduling
- independent browser and HTTP concurrency controls

Celery page tasks reserve one Redis concurrency slot when execution begins and release it when the task exits. Child tasks are sent to Celery without pre-reserving slots. The worker task wrapper reuses one asyncio event loop per worker process, which is compatible with the `--pool=solo` worker model.

Database sessions are opened only for short audit-state reads and result/count writes; page fetch, parsing, and rule evaluation run without an open session. Page-result writes use the database uniqueness constraint on `(audit_id, normalized_url)` with PostgreSQL `ON CONFLICT DO UPDATE` so retries and concurrent deliveries converge on one stored result.

## Failure handling

Page-level failures are isolated and do not stop the whole audit. Site-level failures remain audit-level exceptions.

## Reuse boundary

The experimental pipeline reuses existing components through adapters where possible, but does not modify the current production implementation.
