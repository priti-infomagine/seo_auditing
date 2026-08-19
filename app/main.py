import asyncio
import sys

# Windows + Playwright:
# Playwright's async API requires a Proactor event loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    try:
        await init_db()
    except Exception as exc:
        logger.error(
            f"init_db failed during lifespan: {exc}",
            exc_info=True,
        )

    yield

    try:
        await close_db()
    except Exception as exc:
        logger.error(
            f"close_db failed during lifespan shutdown: {exc}",
            exc_info=True,
        )


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api.router import api_router

app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to the {settings.APP_NAME}!"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    from datetime import datetime, timezone

    try:
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(
            f"Health check failed: {exc}",
            exc_info=True,
        )

        return {
            "status": "unhealthy",
            "service": settings.APP_NAME,
            "error": str(exc),
        }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check():
    from datetime import datetime, timezone
    import redis

    checks = {
        "api": {"status": "healthy"},
        "postgresql": {"status": "unknown"},
        "redis": {"status": "unknown"},
        "celery": {"status": "unknown"},
    }

    try:
        from app.core.database import engine

        conn = await engine.connect()
        await conn.close()

        checks["postgresql"] = {"status": "healthy"}

    except Exception as exc:
        checks["postgresql"] = {
            "status": "unhealthy",
            "error": str(exc),
        }

    try:
        r = redis.from_url(
            str(settings.REDIS_URL),
            socket_timeout=2,
        )

        r.ping()

        checks["redis"] = {"status": "healthy"}

    except Exception as exc:
        checks["redis"] = {
            "status": "unhealthy",
            "error": str(exc),
        }

    try:
        from app.shared.tasks.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active() or {}

        checks["celery"] = {
            "status": "healthy" if active else "no_workers",
            "active_workers": len(active),
        }

    except Exception as exc:
        checks["celery"] = {
            "status": "unhealthy",
            "error": str(exc),
        }

    overall = (
        "healthy"
        if all(
            c["status"] in ("healthy", "no_workers")
            for c in checks.values()
        )
        else "degraded"
    )

    return {
        "status": overall,
        "service": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
 
 
 
@app.get("/debug/asyncio")
async def debug_asyncio():
    loop = asyncio.get_running_loop()

    return {
        "platform": sys.platform,
        "policy": type(asyncio.get_event_loop_policy()).__name__,
        "loop": type(loop).__name__,
    }   