import asyncio
import os
import threading
from typing import AsyncGenerator, Optional

from celery.signals import worker_process_init, worker_process_shutdown
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, engine
from app.core.logger import logger


# Per-worker-process persistent event loop and background thread.
# Created in worker_process_init (after fork), used by run_async() for every
# task, and disposed in worker_process_shutdown. This keeps the SQLAlchemy
# async engine's connection pool bound to a single loop for the entire
# process lifetime while allowing concurrent thread-safe task submission.
_worker_loop: Optional[asyncio.AbstractEventLoop] = None
_worker_thread: Optional[threading.Thread] = None


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


def _run_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        loop.close()


@worker_process_init.connect
def _init_worker_loop(sender, **kwargs):
    """Create a persistent background event loop for this worker process.

    Fires once per worker process after fork/spawn, before any tasks run.
    The loop runs continuously in a daemon thread so run_async() can schedule
    coroutines via run_coroutine_threadsafe without locking the worker thread.
    """
    global _worker_loop, _worker_thread
    if _worker_loop is not None and _worker_loop.is_running():
        return  # already initialized

    try:
        _worker_loop = asyncio.new_event_loop()
        _worker_thread = threading.Thread(
            target=_run_event_loop, args=(_worker_loop,), daemon=True
        )
        _worker_thread.start()

        # Best-effort: clear any connections inherited from parent process.
        future = asyncio.run_coroutine_threadsafe(engine.dispose(), _worker_loop)
        future.result(timeout=10)

        logger.info(
            "Worker process initialized with persistent background event loop (pid=%d)",
            os.getpid(),
        )
    except Exception as exc:
        logger.error("Failed to initialize worker event loop: %s", exc, exc_info=True)


@worker_process_shutdown.connect
def _shutdown_worker_loop(sender, **kwargs):
    """Dispose the engine and stop the background loop on process exit."""
    global _worker_loop, _worker_thread
    if _worker_loop is None or not _worker_loop.is_running():
        return
    try:
        future = asyncio.run_coroutine_threadsafe(engine.dispose(), _worker_loop)
        future.result(timeout=5)
    except Exception:
        pass  # best-effort during shutdown
    finally:
        try:
            _worker_loop.call_soon_threadsafe(_worker_loop.stop)
        except Exception:
            pass
        _worker_loop = None
        _worker_thread = None


def run_async(coro):
    """Run *coro* on the worker process's persistent background event loop.

    Lifecycle (Celery worker):
      1. ``worker_process_init`` creates a dedicated background event loop thread.
      2. ``run_async`` schedules coroutines on that loop via ``run_coroutine_threadsafe``.
      3. Multiple worker threads/tasks can submit coroutines to the loop concurrently.
      4. ``worker_process_shutdown`` disposes the engine and stops the loop.

    Falls back to ``asyncio.run()`` when no persistent worker loop exists
    (e.g. standalone scripts).  When inside an existing active event loop that is
    *not* the worker loop (e.g. ``@pytest.mark.asyncio`` tests), uses
    ``nest_asyncio`` to run on the same loop.

    **Important:** When a persistent worker loop exists, it is *always*
    preferred — even if the caller is already inside a different running loop
    (e.g. ``core_seo.tasks._run_async`` creates a per-task loop).  This ensures
    the SQLAlchemy async engine's connection pool is exclusively accessed from
    one event loop, preventing ``RuntimeError: Future attached to a different
    loop`` when connections cross loop boundaries.
    """
    global _worker_loop

    # 1. Celery worker path: _worker_loop is the single source of truth for
    #    DB connections.  If it's running, route all coroutines through it
    #    regardless of whether the caller has its own event loop.  This
    #    prevents pool contamination: connections created on one loop must
    #    not be reused from another loop (asyncpg raises "attached to a
    #    different loop" when they are).
    if _worker_loop is not None and _worker_loop.is_running():
        # If we are already executing ON _worker_loop (nested call from a
        # coroutine scheduled by run_async itself), run inline via
        # nest_asyncio to avoid a thread hop and a potential deadlock
        # (run_coroutine_threadsafe would work too, but inline is faster).
        try:
            running_loop = asyncio.get_running_loop()
            if running_loop.is_running() and running_loop is _worker_loop:
                import nest_asyncio

                nest_asyncio.apply(running_loop)
                return running_loop.run_until_complete(coro)
        except RuntimeError:
            pass
        # Otherwise (different running loop, or no loop in this thread),
        # submit to _worker_loop via a thread-safe future.  The calling
        # thread blocks on future.result() until the coroutine completes
        # on _worker_loop — this is safe because _worker_loop runs in a
        # separate daemon thread.
        logger.debug(
            "run_async: scheduling coroutine on _worker_loop (pid=%d)", os.getpid()
        )
        future = asyncio.run_coroutine_threadsafe(coro, _worker_loop)
        return future.result()

    # 2. No persistent worker loop (e.g. pytest with @pytest.mark.asyncio,
    #    or standalone scripts started outside Celery).  If we are inside a
    #    running event loop, reuse it with nest_asyncio so that mock
    #    sessions / test fixtures on that loop still work.
    try:
        running_loop = asyncio.get_running_loop()
        if running_loop.is_running():
            import nest_asyncio

            nest_asyncio.apply(running_loop)
            logger.debug(
                "run_async: running on existing loop (pid=%d, not _worker_loop)",
                os.getpid(),
            )
            return running_loop.run_until_complete(coro)
    except RuntimeError:
        pass

    # 3. Fallback for standalone scripts outside Celery with no running loop.
    async def _wrapper():
        try:
            return await coro
        finally:
            try:
                await engine.dispose()
            except Exception:
                pass

    return asyncio.run(_wrapper())

