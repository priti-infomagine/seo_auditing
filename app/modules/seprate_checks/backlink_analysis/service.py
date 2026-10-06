from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from .data_for_seo_client import DataForSEOClient
from .model import BacklinkCheck, BacklinkCheckStatus
from .repository import BacklinkCheckRepository


class DataForSEOConfigurationError(RuntimeError):
    pass


class BacklinkAnalysisService:
    @classmethod
    async def run_check(
        cls,
        target: str,
        evidence_limit: int,
        db: AsyncSession,
    ) -> BacklinkCheck:
        check = await BacklinkCheckRepository(db).create(
            BacklinkCheck(
                target=target,
                evidence_limit=evidence_limit,
                status=BacklinkCheckStatus.PROCESSING.value,
            )
        )
        await db.commit()

        try:
            if not settings.DATAFORSEO_LOGIN or not settings.DATAFORSEO_PASSWORD:
                raise DataForSEOConfigurationError(
                    "DataForSEO credentials are not configured"
                )

            client = DataForSEOClient(
                settings.DATAFORSEO_LOGIN,
                settings.DATAFORSEO_PASSWORD,
            )
            report = await client.get_backlink_summary(target, evidence_limit)
            check.result = report
            check.cost = report[0]["cost"]
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
