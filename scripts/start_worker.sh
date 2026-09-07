#!/usr/bin/env bash
# start_worker.sh
#
# Start a Celery worker for the SEO audit backend, subscribed to the
# right queues. See scripts/start_worker.ps1 for the full explanation
# of why we subscribe to BOTH "crawler" and "audit".
#
# Usage (from the backend root):
#   ./scripts/start_worker.sh
#
# Optional: pass extra queues:
#   ./scripts/start_worker.sh crawler,audit,email
#   ./scripts/start_worker.sh crawler,audit --pool=prefork --concurrency=4

set -euo pipefail

# Resolve backend root (the parent of this scripts/ folder).
BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_ROOT"

QUEUES="${1:-crawler,audit}"
POOL="${POOL:-solo}"
CONCURRENCY="${CONCURRENCY:-1}"
LOGLEVEL="${LOGLEVEL:-info}"

echo "============================================================"
echo " SEO Audit Tool — Celery worker"
echo "============================================================"
echo "Backend root : $BACKEND_ROOT"
echo "Queues       : $QUEUES"
echo "Pool         : $POOL (concurrency=$CONCURRENCY)"
echo "Log level    : $LOGLEVEL"
echo ""
echo "Queue topology reminder:"
echo "  POST /audit/analyze  -> enqueues 'crawler.crawl_website'  to 'crawler'"
echo "  crawler.crawl_website -> enqueues 'audit.run_analysis_pipeline' to 'audit'"
echo ""
echo "Press Ctrl+C to stop."
echo "============================================================"

# Use whichever python is on PATH (set PYTHON=python3.11 to override).
PYTHON="${PYTHON:-python}"

exec "$PYTHON" -m celery \
    --app=app.shared.tasks.celery_app \
    worker \
    --loglevel="$LOGLEVEL" \
    -Q "$QUEUES" \
    --pool="$POOL" \
    --concurrency="$CONCURRENCY" \
    --without-gossip \
    --without-mingle \
    --without-heartbeat
