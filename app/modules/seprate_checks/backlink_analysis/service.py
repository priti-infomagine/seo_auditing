from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from .data_for_seo_client import DataForSEOClient
from .model import BacklinkCheck, BacklinkCheckStatus
from .repository import BacklinkCheckRepository

_dataforseo_client: DataForSEOClient | None = None
_dataforseo_credentials: tuple[str, str] | None = None


class DataForSEOConfigurationError(RuntimeError):
    pass


async def close_dataforseo_client() -> None:
    global _dataforseo_client, _dataforseo_credentials
    if _dataforseo_client is not None:
        await _dataforseo_client.aclose()
    _dataforseo_client = None
    _dataforseo_credentials = None


async def _get_dataforseo_client(login: str, password: str) -> DataForSEOClient:
    global _dataforseo_client, _dataforseo_credentials
    credentials = (login, password)
    if _dataforseo_credentials != credentials:
        await close_dataforseo_client()
        _dataforseo_client = DataForSEOClient(login, password)
        _dataforseo_credentials = credentials
    return _dataforseo_client


class BacklinkAnalysisService:
    @classmethod
    async def run_check(
        cls,
        target: str,
        db: AsyncSession,
    ) -> BacklinkCheck:
        check = await BacklinkCheckRepository(db).create(
            BacklinkCheck(
                target=target,
                status=BacklinkCheckStatus.PROCESSING.value,
                evidence_limit=100,
            )
        )

        try:
            if not settings.DATAFORSEO_LOGIN or not settings.DATAFORSEO_PASSWORD:
                raise DataForSEOConfigurationError(
                    "DataForSEO credentials are not configured"
                )

            client = await _get_dataforseo_client(
                settings.DATAFORSEO_LOGIN,
                settings.DATAFORSEO_PASSWORD,
            )
            report = await client.get_backlink_summary(target)
            check.result = report
            check.cost = report["cost"]
            check.status = BacklinkCheckStatus.COMPLETED.value
            check.error = None
            await db.commit()
            await db.refresh(check)
            return check
        except Exception as exc:
            check.status = BacklinkCheckStatus.FAILED.value
            check.error = str(exc)
            await db.commit()
            raise
