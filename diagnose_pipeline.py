"""
Pipeline Stage Diagnostic — pinpoints exactly where an audit pipeline stopped.

Checks each stage of the crawl -> parse -> evaluate -> score pipeline for a given
project_id and crawl_id, reports row counts, status, and where the flow broke.

Usage (from backend/ root):
    python diagnose_pipeline.py --project-id cb6d83e2-74a4-4333-821b-a3f023c9e5ce --crawl-id 30239758-6a84-45fd-8580-ba593034127c
    python diagnose_pipeline.py --project-id cb6d83e2-74a4-4333-821b-a3f023c9e5ce
    python diagnose_pipeline.py --crawl-id 30239758-6a84-45fd-8580-ba593034127c
"""
import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # Fix Windows console encoding for emoji/output
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from uuid import UUID

from app.core.config import settings
from app.core.database import async_session_factory
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.audit.models.parsed_page_facts import ParsedPageFact
from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult
from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun


async def diagnose(project_id: UUID | None, crawl_id: UUID | None):
    async with async_session_factory() as db:
        print("=" * 70)
        print("PIPELINE STAGE DIAGNOSTIC")
        print("=" * 70)

        # ── Resolve crawl_id / project_id from each other if only one given ──
        if crawl_id and not project_id:
            job = await db.get(CrawlJob, crawl_id)
            if job:
                project_id = job.project_id
                print(f"Resolved project_id={project_id} from crawl_id={crawl_id}")
            else:
                print(f"CrawlJob not found for crawl_id={crawl_id}")
                return

        if project_id and not crawl_id:
            # Try SeoAnalysisRun first
            run = await db.execute(
                __import__("sqlalchemy").select(SeoAnalysisRun).where(
                    SeoAnalysisRun.project_id == project_id
                )
            )
            run = run.scalar_one_or_none()
            if run:
                crawl_id = run.crawl_id
                print(f"Resolved crawl_id={crawl_id} from SeoAnalysisRun project_id={project_id}")
            else:
                # Fall back to CrawlJob
                from sqlalchemy import select
                job_result = await db.execute(
                    select(CrawlJob).where(CrawlJob.project_id == project_id)
                )
                job = job_result.scalar_one_or_none()
                if job:
                    crawl_id = job.id
                    print(f"Resolved crawl_id={crawl_id} from CrawlJob project_id={project_id}")
                else:
                    print(f"No CrawlJob found for project_id={project_id}")
                    return

        print(f"\nProject ID: {project_id}")
        print(f"Crawl ID:   {crawl_id}")
        print("-" * 70)

        # ── Stage 0: CrawlJob ──
        from sqlalchemy import select, func
        job = await db.get(CrawlJob, crawl_id) if crawl_id else None
        if job:
            print(f"\n[STAGE 0] CrawlJob")
            print(f"  Status:          {job.status}")
            print(f"  URL:             {job.url}")
            print(f"  Domain:          {job.domain}")
            print(f"  Pages discovered:{job.pages_discovered}")
            print(f"  Pages crawled:   {job.pages_crawled}")
            print(f"  Started at:      {job.started_at}")
            print(f"  Completed at:    {job.completed_at}")
            print(f"  Duration (ms):   {job.duration_ms}")
            print(f"  Error:           {job.error or 'None'}")
            print(f"  auto_analyze:    {job.crawl_config.get('auto_analyze') if job.crawl_config else 'N/A'}")
        else:
            print(f"\n[STAGE 0] CrawlJob: NOT FOUND for crawl_id={crawl_id}")
            return

        # ── Stage 1: Crawl Pages ──
        pages_result = await db.execute(
            select(func.count()).select_from(CrawlPage).where(CrawlPage.crawl_id == crawl_id)
        )
        pages_count = pages_result.scalar_one()

        success_result = await db.execute(
            select(func.count()).select_from(CrawlPage).where(
                CrawlPage.crawl_id == crawl_id,
                CrawlPage.is_success == True,
            )
        )
        success_count = success_result.scalar_one()

        print(f"\n[STAGE 1] Crawl Pages")
        print(f"  Total pages:     {pages_count}")
        print(f"  Successful:      {success_count}")
        print(f"  Failed:          {pages_count - success_count}")

        if pages_count == 0:
            print("\n  [STOP] PIPELINE STOPPED: No pages crawled. Check crawler task logs.")
            return

        # ── Stage 1b: Snapshots ──
        snapshot_result = await db.execute(
            select(func.count()).select_from(PageSnapshot).where(
                PageSnapshot.page_id.in_(
                    select(CrawlPage.id).where(CrawlPage.crawl_id == crawl_id)
                )
            )
        )
        snapshot_count = snapshot_result.scalar_one()
        print(f"  Snapshots:       {snapshot_count}")

        # ── Stage 1c: SEO Data ──
        seo_result = await db.execute(
            select(func.count()).select_from(PageSEOData).where(
                PageSEOData.page_id.in_(
                    select(CrawlPage.id).where(CrawlPage.crawl_id == crawl_id)
                )
            )
        )
        seo_count = seo_result.scalar_one()
        print(f"  SEO data rows:   {seo_count}")

        # ── Stage 1d: Network Data ──
        network_result = await db.execute(
            select(func.count()).select_from(PageNetworkData).where(
                PageNetworkData.page_id.in_(
                    select(CrawlPage.id).where(CrawlPage.crawl_id == crawl_id)
                )
            )
        )
        network_count = network_result.scalar_one()
        print(f"  Network data:    {network_count}")

        # ── Stage 2: Parse (ParsedPageFacts) ──
        parsed_result = await db.execute(
            select(func.count()).select_from(ParsedPageFact).where(
                ParsedPageFact.crawl_id == crawl_id,
                ParsedPageFact.project_id == project_id,
            )
        )
        parsed_count = parsed_result.scalar_one()
        print(f"\n[STAGE 2] Parse (ParsedPageFacts)")
        print(f"  Parsed facts:    {parsed_count}")

        if parsed_count == 0:
            if snapshot_count == 0:
                print("\n  [STOP] PIPELINE STOPPED: No HTML snapshots to parse. Crawler did not persist snapshots.")
            else:
                print("\n  [STOP] PIPELINE STOPPED: Parse stage did not run. Check audit.parse_crawl Celery task.")
            return

        # ── Stage 3: Evaluate (RuleEvaluationResults) ──
        eval_result = await db.execute(
            select(func.count()).select_from(RuleEvaluationResult).where(
                RuleEvaluationResult.crawl_id == crawl_id,
                RuleEvaluationResult.project_id == project_id,
            )
        )
        eval_count = eval_result.scalar_one()

        # Distinct pages evaluated
        eval_pages_result = await db.execute(
            select(func.count(func.distinct(RuleEvaluationResult.page_id))).where(
                RuleEvaluationResult.crawl_id == crawl_id,
                RuleEvaluationResult.project_id == project_id,
            )
        )
        eval_pages_count = eval_pages_result.scalar_one()

        print(f"\n[STAGE 3] Evaluate (RuleEvaluationResults)")
        print(f"  Total results:   {eval_count}")
        print(f"  Pages evaluated: {eval_pages_count}")

        if eval_count == 0:
            print("\n  [STOP] PIPELINE STOPPED: Rule evaluation did not run. Check audit.evaluate_rules Celery task.")
            return

        # ── Stage 4: Score (SeoAnalysisRun) ──
        run_result = await db.execute(
            select(SeoAnalysisRun).where(SeoAnalysisRun.project_id == project_id)
        )
        run = run_result.scalar_one_or_none()
        print(f"\n[STAGE 4] Score (SeoAnalysisRun)")
        if run:
            print(f"  Overall score:   {run.overall_score}")
            print(f"  Grade:           {run.grade}")
            print(f"  Pages scored:    {run.total_pages_scored}")
            print(f"  Rules evaluated: {run.total_rules_evaluated}")
            print(f"  Passed:          {run.total_passed}")
            print(f"  Failed:          {run.total_failed}")
            print(f"  Critical issues: {run.critical_issues}")
            print(f"  Status:          {run.analysis_status}")
            print(f"  Scored at:       {run.scored_at}")
            print(f"  Output file:     {run.output_file_path}")
        else:
            print(f"  NOT FOUND")
            print("\n  [STOP] PIPELINE STOPPED: Scoring did not run. Check audit.score_project Celery task.")
            return

        # ── Final Summary ──
        print("\n" + "=" * 70)
        print("PIPELINE SUMMARY")
        print("=" * 70)
        stages = [
            ("Crawl (pages)", pages_count > 0, f"{pages_count} pages"),
            ("Snapshots", snapshot_count > 0, f"{snapshot_count} snapshots"),
            ("Parse", parsed_count > 0, f"{parsed_count} facts"),
            ("Evaluate", eval_count > 0, f"{eval_count} results"),
            ("Score", run is not None, f"score={run.overall_score}" if run else "N/A"),
        ]

        all_ok = True
        for name, ok, detail in stages:
            status = "[OK]" if ok else "[FAIL]"
            print(f"  {status} {name:<20} {detail}")
            if not ok:
                all_ok = False

        if all_ok:
            print("\n[+] Pipeline completed successfully for all stages.")
            if job and job.status != "completed":
                print(f"   [!] CrawlJob status is '{job.status}' — should be 'completed'.")
                print("      This means the analysis ran but the crawl job status was not updated.")
        else:
            print("\n[-] Pipeline did NOT complete. See [STOP] markers above for the failure point.")


async def retrigger_pipeline(project_id: UUID, crawl_id: UUID):
    """Re-enqueue the analysis pipeline for a stuck audit."""
    from app.shared.tasks.celery_app import celery_app

    print("\n" + "=" * 70)
    print("RE-TRIGGERING ANALYSIS PIPELINE")
    print("=" * 70)
    print(f"  project_id: {project_id}")
    print(f"  crawl_id:   {crawl_id}")

    # Verify crawl job exists and is completed
    async with async_session_factory() as db:
        job = await db.get(CrawlJob, crawl_id)
        if not job:
            print(f"\n[ERROR] CrawlJob not found for crawl_id={crawl_id}")
            return
        if job.status != "completed":
            print(f"\n[WARNING] CrawlJob status is '{job.status}' (not 'completed').")
            print("          The analysis pipeline may fail if pages are still being crawled.")

    # Enqueue the pipeline task
    result = celery_app.send_task(
        "audit.run_analysis_pipeline",
        args=[str(project_id), str(crawl_id)],
        queue="audit",
    )
    print(f"\n[OK] Task enqueued: audit.run_analysis_pipeline")
    print(f"     task_id: {result.id}")
    print(f"     queue:   audit")
    print(f"\n     Ensure a Celery worker is running on the 'audit' queue:")
    print(f"     celery -A app.shared.tasks worker -l info -Q audit")


def main():
    parser = argparse.ArgumentParser(description="Diagnose where an audit pipeline stopped.")
    parser.add_argument("--project-id", type=str, default=None, help="Project UUID")
    parser.add_argument("--crawl-id", type=str, default=None, help="Crawl UUID")
    parser.add_argument("--retrigger", action="store_true", help="Re-enqueue the analysis pipeline if stuck")
    args = parser.parse_args()

    if not args.project_id and not args.crawl_id:
        parser.error("At least one of --project-id or --crawl-id is required")

    project_id = UUID(args.project_id) if args.project_id else None
    crawl_id = UUID(args.crawl_id) if args.crawl_id else None

    if args.retrigger:
        if not project_id or not crawl_id:
            parser.error("--retrigger requires both --project-id and --crawl-id")
        asyncio.run(retrigger_pipeline(project_id, crawl_id))
    else:
        asyncio.run(diagnose(project_id, crawl_id))


if __name__ == "__main__":
    main()
