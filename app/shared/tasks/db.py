import asyncio
import os
from typing import AsyncGenerator, Optional

from celery.signals import worker_process_init, worker_process_shutdown
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, engine
from app.core.logger import logger


# Per-worker-process persistent event loop.
# Created in worker_process_init (after fork), used by run_async() for every
# task, and disposed in worker_process_shutdown.  This keeps the SQLAlchemy
# async engine's connection pool bound to a single loop for the entire
# process lifetime, eliminating the "Event loop is closed" errors that
# previously required disposing the pool after every task.
_worker_loop: Optional[asyncio.AbstractEventLoop] = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@worker_process_init.connect
def _init_worker_loop(sender, **kwargs):
    """Create a persistent event loop for this worker process.

    Fires once per worker process after fork/spawn, before any tasks run.
    The loop is reused by every run_async() call in this process so the
    engine's connection pool stays on one loop — no per-task disposal needed.
    """
    global _worker_loop
    if _worker_loop is not None:
        return  # already initialized
    try:
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
        # Best-effort: clear any connections inherited from the parent process.
        # Normally a no-op since the engine is lazy (no connections until first use).
        _worker_loop.run_until_complete(engine.dispose())
        logger.info("Worker process initialized with persistent event loop (pid=%d)", os.getpid())
    except Exception as exc:
        logger.error("Failed to initialize worker event loop: %s", exc, exc_info=True)


@worker_process_shutdown.connect
def _shutdown_worker_loop(sender, **kwargs):
    """Dispose the engine and close the loop once, right before process exit."""
    global _worker_loop
    if _worker_loop is None:
        return
    try:
        _worker_loop.run_until_complete(engine.dispose())
    except Exception:
        pass  # best-effort during shutdown
    finally:
        try:
            _worker_loop.close()
        except Exception:
            pass
        _worker_loop = None


def run_async(coro):
    """Run *coro* on the worker process's persistent event loop.

    Lifecycle (Celery prefork worker):
      1. ``worker_process_init`` creates a dedicated event loop.
      2. ``run_async`` schedules coroutines on that same loop for every task.
      3. ``worker_process_shutdown`` disposes the engine on that same loop.

    The entire SQLAlchemy engine connection pool is created once per worker
    process and reused across tasks — it is NOT recreated or disposed per task.

    Falls back to ``asyncio.run()`` (with per-run disposal) when no persistent
    loop exists (e.g. tests, standalone scripts outside Celery).
    """
    if _worker_loop is not None:
        return _worker_loop.run_until_complete(coro)

    # Fallback for non-Celery contexts (tests, standalone scripts).
    # Still dispose per-run to avoid "Event loop is closed" errors since
    # the singleton engine may have connections bound to a previous loop.
    async def _wrapper():
        try:
            return await coro
        finally:
            try:
                await engine.dispose()
            except Exception:
                pass  # best-effort; non-fatal during shutdown

    return asyncio.run(_wrapper())
