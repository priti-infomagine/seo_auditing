import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository


class AuditRetriever:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = SeoAnalysisRunRepository(db)

    async def get_latest_completed(self, project_id: UUID) -> Optional[dict]:
        run = await self.repo.get_by_project_id(project_id)
        if run is not None and run.analysis_status == "completed" and run.overall_score is not None:
            return {
                "id": run.id,
                "project_id": run.project_id,
                "crawl_id": run.crawl_id,
                "domain": run.domain,
                "overall_score": float(run.overall_score),
                "grade": run.grade,
                "total_pages_scored": run.total_pages_scored,
                "total_rules_evaluated": run.total_rules_evaluated,
                "total_passed": run.total_passed,
                "total_failed": run.total_failed,
                "critical_issues": run.critical_issues,
                "warnings": run.warnings,
                "category_scores": run.category_scores or {},
                "top_issues": run.top_issues or {},
                "scored_at": run.scored_at.isoformat() if run.scored_at else None,
            }

        fallback = self._load_from_output_file(project_id)
        if fallback is not None:
            return fallback
        return None

    def _load_from_output_file(self, project_id: UUID) -> Optional[dict]:
        try:
            output_dir = Path(__file__).resolve().parents[4] / "app" / "output"
            matches = sorted(output_dir.glob(f"*_{project_id}.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not matches:
                return None
            with matches[0].open("r", encoding="utf-8") as f:
                data = json.load(f)
            summary = data.get("summary") or {}
            categories = data.get("categories") or {}
            category_scores = {c.get("id") or c.get("name"): c.get("score") for c in categories}
            return {
                "id": None,
                "project_id": str(project_id),
                "crawl_id": data.get("audit", {}).get("crawl_id"),
                "domain": data.get("audit", {}).get("domain"),
                "overall_score": summary.get("score"),
                "grade": summary.get("health"),
                "total_pages_scored": summary.get("total_pages"),
                "total_rules_evaluated": summary.get("total_checks"),
                "total_passed": summary.get("checks", {}).get("passed"),
                "total_failed": summary.get("checks", {}).get("failed"),
                "critical_issues": summary.get("issues", {}).get("critical"),
                "warnings": summary.get("issues", {}).get("high"),
                "category_scores": category_scores,
                "top_issues": summary.get("top_issues") or {},
                "scored_at": datetime.utcfromtimestamp(matches[0].stat().st_mtime).isoformat(),
            }
        except Exception:
            return None

