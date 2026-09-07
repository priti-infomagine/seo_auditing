"""Shared bounded ThreadPoolExecutor for CPU-bound crawler work.

A dedicated, shared, bounded executor is used instead of
``asyncio.to_thread`` (which uses the default loop executor with up to
``min(32, os.cpu_count() + 4)`` workers).  In a Celery worker process that
already competes for CPU, an unbounded pool causes excessive context
switching for CPU-bound parsing/compression work.  Capping at
``min(os.cpu_count(), 4)`` keeps per-process parallelism sane.

The executor is module-level so it is shared across all calls within a
single worker process.  ``ThreadPoolExecutor`` is lazy — threads are
created on demand and reused.  In a Celery prefork worker each child
process gets its own instance after fork.
"""
import os
from concurrent.futures import ThreadPoolExecutor

_cpu_bound_executor = ThreadPoolExecutor(
    max_workers=min(os.cpu_count() or 1, 4),
    thread_name_prefix="crawler-cpu-bound",
)

# Module-level accessor for import by orchestrator and persistence service.
cpu_bound_executor = _cpu_bound_executor
