from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logger import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────────────────────
    # logger.info("Application startup: initializing database")
    await init_db()
    # logger.info("Application startup: database initialized successfully")
    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    # logger.info("Application shutdown: closing database connections")
    await close_db()
    # logger.info("Application shutdown: database connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)
# ── CORS ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────
from app.api.router import api_router  

app.include_router(api_router)


# ── Root health-check (kept for convenience) ─────────────────────────
@app.get("/")
async def root():
    logger.info("GET / - Root endpoint called")
    return {"message": f"Welcome to the {settings.APP_NAME}!"}


@app.get("/health", tags=["Health"])
async def health_check():
    from datetime import datetime, timezone

    logger.info("GET /health - Health check endpoint called")
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
