# Audit WebSocket Event Streaming - Client Integration Guide

## Overview

The SEO Audit API now supports real-time progress streaming via WebSocket. This allows clients to receive live updates during the audit pipeline instead of polling HTTP endpoints.

## WebSocket Endpoint

```
WS /api/v1/audit/ws/{audit_id}
```

## Connection

### 1. Start an Audit

```bash
POST /api/v1/audit/analyze
Content-Type: application/json

{
  "url": "https://example.com",
  "concurrency": 10,
  "full_pipeline": true
}
```

### 2. Response includes `websocket_url`

```json
{
  "success": true,
  "status": "queued",
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_id": "celery-task-id",
  "websocket_url": "/api/v1/audit/ws/550e8400-e29b-41d4-a716-446655440000",
  "task_status_url": "/api/v1/audit/analyze/task/celery-task-id",
  "crawl_status_url": "/api/v1/crawler/status/550e8400-e29b-41d4-a716-446655440000",
  "pipeline_status_url": "/api/v1/audit/status/550e8400-e29b-41d4-a716-446655440000",
  "result_url": "/api/v1/audit/result/550e8400-e29b-41d4-a716-446655440000",
  "poll_url": "/api/v1/audit/analyze/poll/550e8400-e29b-41d4-a716-446655440000",
  "full_pipeline": true
}
```

### 3. Connect to WebSocket

```javascript
const auditId = "550e8400-e29b-41d4-a716-446655440000";
const ws = new WebSocket(`ws://your-api-host/api/v1/audit/ws/${auditId}`);

ws.onopen = () => console.log("Connected to audit stream");
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  handleAuditEvent(msg);
};
ws.onclose = (event) => console.log("Disconnected:", event.reason);
```

## Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `last_id` | string | (from start) | Redis stream entry ID to resume from |
| `detail` | boolean | false | Emit granular `rule_checked` events (debug mode) |

### Resume Example

```javascript
// Resume from last known event ID
const ws = new WebSocket(`ws://host/api/v1/audit/ws/${auditId}?last_id=1523456789012-0`);
```

### Debug Mode Example

```javascript
// Receive individual rule_checked events (60+ per page)
const ws = new WebSocket(`ws://host/api/v1/audit/ws/${auditId}?detail=true`);
```

## Message Format

All messages are JSON objects with a `type` field.

### Progress Event

```json
{
  "type": "event",
  "event_type": "crawl_page_started",
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://example.com/page1",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "seq": 5,
  "payload": {
    "depth": 0,
    "parent_page_id": null
  },
  "category": "crawl"
}
```

### Final Snapshot

```json
{
  "type": "final",
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "summary": {
    "score": 85,
    "grade": "B",
    "pages": {"analyzed": 50, "total": 50},
    "checks": {"passed": 2800, "failed": 200}
  },
  "pages": [
    {"url": "https://example.com/", "score": 90, "issues": [...]},
    {"url": "https://example.com/about", "score": 82, "issues": [...]}
  ],
  "status": "completed"
}
```

### Error Event

```json
{
  "type": "error",
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Audit pipeline failed",
  "code": "PIPELINE_FAILED"
}
```

### Close Event

```json
{
  "type": "close",
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "reason": "Audit completed"
}
```

## Event Types by Category

### Crawl Events

| Event | Description | Payload |
|-------|-------------|---------|
| `crawl_started` | Crawl phase began | `start_url`, `max_depth`, `max_pages` |
| `crawl_page_started` | Page crawl started | `depth`, `parent_page_id` |
| `crawl_page_fetched` | HTTP fetch completed | `success`, `error` |
| `crawl_page_persisted` | Page saved to DB | `page_id` |
| `crawl_page_failed` | Page crawl failed | `error` |
| `crawl_complete` | Crawl phase finished | `pages_crawled`, `pages_discovered`, `duration_ms` |

### Parse Events

| Event | Description | Payload |
|-------|-------------|---------|
| `parse_started` | Parse phase began | - |
| `parse_page_complete` | Page parsed | `page_id`, `parsed_count` |
| `parse_complete` | Parse phase finished | `pages_parsed`, `pages_failed`, `pages_skipped` |

### Evaluate Events

| Event | Description | Payload |
|-------|-------------|---------|
| `evaluate_started` | Rule evaluation began | - |
| `evaluate_page_complete` | Page evaluated (batched) | `page_id`, `rules_passed`, `rules_failed`, `rules_total`, `rules[]` |
| `evaluate_complete` | Evaluation finished | `pages_evaluated`, `rules_run`, `total_results` |

> **Note**: By default, rule results are batched per page (`evaluate_page_complete`). Use `?detail=true` to receive individual `rule_checked` events (60+ per page).

### Score Events

| Event | Description | Payload |
|-------|-------------|---------|
| `score_started` | Scoring phase began | - |
| `score_complete` | Scoring finished | `overall_score`, `grade`, `pages_analyzed` |

### Pipeline Events

| Event | Description | Payload |
|-------|-------------|---------|
| `pipeline_started` | Full pipeline started | - |
| `pipeline_completed` | Pipeline succeeded | `summary` |
| `pipeline_failed` | Pipeline failed | `error` |

## Event Categories

Each event includes a `category` field for frontend routing:

- `crawl` - Crawl phase events
- `parse` - Parse phase events
- `evaluate` - Rule evaluation events
- `score` - Scoring events
- `pipeline` - Pipeline lifecycle events

## Complete Client Example

```javascript
class AuditWebSocketClient {
  constructor(auditId, options = {}) {
    this.auditId = auditId;
    this.options = options;
    this.ws = null;
    this.lastEventId = null;
    this.handlers = new Map();
  }

  connect() {
    const params = new URLSearchParams();
    if (this.options.lastEventId) params.set('last_id', this.options.lastEventId);
    if (this.options.detail) params.set('detail', 'true');

    const url = `ws://your-api-host/api/v1/audit/ws/${this.auditId}?${params}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => this.emit('open');
    this.ws.onmessage = (event) => this.handleMessage(JSON.parse(event.data));
    this.ws.onclose = (event) => this.emit('close', event);
    this.ws.onerror = (error) => this.emit('error', error);
  }

  handleMessage(msg) {
    switch (msg.type) {
      case 'event':
        this.lastEventId = `${msg.seq}-0`; // Approximate Redis entry ID
        this.emit(msg.category, msg);
        this.emit('event', msg);
        break;
      case 'final':
        this.emit('final', msg);
        this.emit('complete', msg.summary);
        break;
      case 'error':
        this.emit('error', new Error(msg.message));
        break;
      case 'close':
        this.emit('close', msg);
        break;
    }
  }

  on(event, handler) {
    if (!this.handlers.has(event)) this.handlers.set(event, []);
    this.handlers.get(event).push(handler);
  }

  emit(event, ...args) {
    (this.handlers.get(event) || []).forEach(h => h(...args));
  }

  disconnect() {
    if (this.ws) this.ws.close();
  }

  getResumeUrl() {
    return `/api/v1/audit/ws/${this.auditId}?last_id=${this.lastEventId}`;
  }
}

// Usage
const client = new AuditWebSocketClient(auditId, { detail: false });

client.on('crawl', (msg) => {
  console.log(`Crawling: ${msg.url} (${msg.payload.depth || 0})`);
});

client.on('parse', (msg) => {
  console.log(`Parsed page ${msg.payload.parsed_count}`);
});

client.on('evaluate', (msg) => {
  console.log(`Evaluated ${msg.payload.rules_passed}/${msg.payload.rules_total} rules for ${msg.url}`);
});

client.on('score', (msg) => {
  console.log(`Scoring: ${msg.payload.overall_score}/100 (Grade ${msg.payload.grade})`);
});

client.on('final', (msg) => {
  console.log('Audit complete!', msg.summary);
  renderReport(msg.pages);
});

client.on('error', (err) => {
  console.error('Audit failed:', err.message);
});

client.connect();

// For resume capability after disconnect
window.addEventListener('beforeunload', () => {
  localStorage.setItem('audit_resume_url', client.getResumeUrl());
});
```

## Fallback to Polling

If WebSocket is unavailable, fall back to HTTP polling:

```javascript
async function pollAudit(auditId) {
  const response = await fetch(`/api/v1/audit/analyze/poll/${auditId}`);
  const data = await response.json();

  if (data.status === 'completed') {
    return data.result;
  }

  // Update UI with progress
  updateProgress(data.stage, data.pages_parsed);

  // Poll again in 5 seconds
  await new Promise(r => setTimeout(r, 5000));
  return pollAudit(auditId);
}
```

## Feature Flag

WebSocket streaming can be disabled server-side via environment variable:

```bash
AUDIT_WS_ENABLED=false
```

When disabled, the WebSocket endpoint returns a 1011 error and clients should use polling.

## Redis Stream Details

- **Stream key**: `audit:events:{audit_id}`
- **Max length**: 10,000 entries
- **TTL**: 1 hour (3600 seconds)
- **Entry format**: `{"event": "<json_payload>"}`

## Performance Notes

- **Event batching**: Rule evaluations are batched per page (1 event per page with 60 rules) instead of 60 individual events
- **Detail mode**: Use `?detail=true` for granular per-rule events (debug only)
- **Resume**: Use `last_id` parameter to resume from interruption
- **Memory**: Each audit stream uses ~50MB max (10K entries × ~500 bytes)

## Error Handling

| Code | Meaning | Action |
|------|---------|--------|
| 1000 | Normal closure | Reconnect if needed |
| 1006 | Abnormal closure | Reconnect with `last_id` |
| 1011 | Server error | Check server logs, fallback to polling |

## Migration from Polling

| Old Approach | New Approach |
|--------------|--------------|
| `GET /audit/analyze/poll/{id}` every 5s | `WS /audit/ws/{id}` (push) |
| `GET /audit/status/{id}` every 10s | Real-time events |
| `GET /audit/result/{id}` at end | `final` event at end |

All polling endpoints remain functional for backward compatibility.