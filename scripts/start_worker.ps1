# start_worker.ps1
#
# Start a Celery worker for the SEO audit backend, subscribed to the
# right queues.
#
# Why a script: the audit pipeline spans TWO queues:
#
#   POST /audit/analyze
#     -> enqueues `crawler.crawl_website`           on queue "crawler"
#        (consumed by the worker's "crawler" subscription)
#   crawler.crawl_website (on completion)
#     -> enqueues `audit.run_analysis_pipeline`     on queue "audit"
#        (consumed by the worker's "audit" subscription)
#
# If the worker is started with `-Q audit` only, the very first
# `crawler.crawl_website` task sits in Redis forever and the audit never
# progresses. This script subscribes to BOTH queues by default.
#
# The Celery app lives in `app.shared.tasks.celery_app` (NOT
# `app.shared.tasks`) — Celery resolves `-A <module>` to a module that
# must contain a `celery` or `app` attribute. Pointing at the file
# itself is the safest way on Windows.
#
# Usage (from the backend root):
#   powershell -ExecutionPolicy Bypass -File scripts\start_worker.ps1
#
# Optional: pass extra queues to subscribe to, e.g.
#   powershell -ExecutionPolicy Bypass -File scripts\start_worker.ps1 -Queues "crawler,audit,email"

param(
    [string]$Queues = "crawler,audit",
    [string]$LogLevel = "info",
    [string]$Pool = "solo",
    [int]$Concurrency = 1
)

$ErrorActionPreference = "Stop"

# Resolve backend root (the parent of this scripts/ folder).
$BackendRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $BackendRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SEO Audit Tool — Celery worker" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ("Backend root : {0}" -f $BackendRoot)
Write-Host ("Queues       : {0}" -f $Queues)
Write-Host ("Pool         : {0} (concurrency={1})" -f $Pool, $Concurrency)
Write-Host ("Log level    : {0}" -f $LogLevel)
Write-Host ""
Write-Host "Queue topology reminder:" -ForegroundColor Yellow
Write-Host "  POST /audit/analyze  -> enqueues 'crawler.crawl_website'  to 'crawler'"
Write-Host "  crawler.crawl_website -> enqueues 'audit.run_analysis_pipeline' to 'audit'"
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan

# Use the system Python. The Celery entry point is the FILE
# (app.shared.tasks.celery_app) so Celery finds the celery_app
# instance regardless of how the file is named on disk.
$Python = "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
if (-not (Test-Path $Python)) {
    # Fall back to whatever 'python' is on PATH.
    $Python = "python"
}

& $Python -m celery `
    --app=app.shared.tasks.celery_app `
    worker `
    --loglevel=$LogLevel `
    -Q $Queues `
    --pool=$Pool `
    --concurrency=$Concurrency `
    --without-gossip `
    --without-mingle `
    --without-heartbeat
