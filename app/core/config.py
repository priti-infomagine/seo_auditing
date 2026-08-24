from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "Automated SEO & Website Audit Tool"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # Set to True in production (HTTPS)
    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/seo_audit"
    DATABASE_SYNC_URL: Optional[str] = None  # for alembic migrations

    @property
    def sync_database_url(self) -> str:
        """Return a sync-compatible URL (psycopg2) for Alembic."""
        if self.DATABASE_SYNC_URL:
            return self.DATABASE_SYNC_URL
        # Replace asyncpg driver with psycopg2 for sync operations
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")

    # ── Redis / Cache ────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_BROKER_URL: str = "redis://localhost:6379/0"
    REDIS_BACKEND_URL: str = "redis://localhost:6379/1"

    # ── Email (SMTP) ─────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@seoaudit.local"

    # ── OTP ──────────────────────────────────────────────────────────
    OTP_EXPIRE_MINUTES: int = 10
    CRAWL_MAX_PAGES: int = 100

    # ── Timezone ─────────────────────────────────────────────────────
    TZ: str = "UTC"

    # ── CORS ─────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── External APIs ────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    GOOGLE_PAGESPEED_API_KEY: str = ""

    # ── SEO Scorer Weights ──────────────────────────────────────────
    # JSON object mapping category -> weight. Weights are normalized to sum=1.
    # Example: '{"on_page": 0.25, "technical": 0.15, "content": 0.20, "links": 0.10, "images": 0.05, "schema": 0.05, "social": 0.05, "security": 0.10, "accessibility": 0.05, "performance": 0.05}'
    SEO_SCORER_WEIGHTS: Optional[str] = None


settings = Settings()
