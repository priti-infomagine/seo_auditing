from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────────────────────
    await init_db()
    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    await close_db()


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
from app.apis.router import api_router  # noqa: E402

app.include_router(api_router)


# ── Root health-check (kept for convenience) ─────────────────────────
@app.get("/")
async def root():
    return {"message": f"Welcome to the {settings.APP_NAME}!"}


@app.get("/health", tags=["Health"])
async def health_check():
    from datetime import datetime, timezone

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }