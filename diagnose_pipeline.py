"""
Pipeline Stage Diagnostic — pinpoints exactly where an audit pipeline stopped.

Checks each stage of the crawl -> parse -> evaluate -> score pipeline for a given
audit_id (== crawl_id), reports row counts, status, and where the flow broke.

Usage (from backend/ root):
    python diagnose_pipeline.py --audit-id 30239758-6a84-45fd-8580-ba593034127c
"""
import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from uuid import UUID

from app.core.database import async_session_factory
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.audit.models.parsed_page_facts import ParsedPageFact
from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult
from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun


async def diagnose(audit_id: UUID):
    async with async_session_factory() as db:
        print("=" * 70)
        print("PIPELINE STAGE DIAGNOSTIC")
        print("=" * 70)

        print(f"\nAudit ID: {audit_id}")
        print("-" * 70)

        # ── Stage 0: CrawlJob ──
        from sqlalchemy import select, func
        job = await db.get(CrawlJob, audit_id)
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
            print(f"\n[STAGE 0] CrawlJob: NOT FOUND for audit_id={audit_id}")
            return

        # ── Stage 1: Crawl Pages ──
        pages_result = await db.execute(
            select(func.count()).select_from(CrawlPage).where(CrawlPage.crawl_id == audit_id)
        )
        pages_count = pages_result.scalar_one()

        success_result = await db.execute(
            select(func.count()).select_from(CrawlPage).where(
                CrawlPage.crawl_id == audit_id,
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
                    select(CrawlPage.id).where(CrawlPage.crawl_id == audit_id)
                )
            )
        )
        snapshot_count = snapshot_result.scalar_one()
        print(f"  Snapshots:       {snapshot_count}")

        # ── Stage 1c: SEO Data ──
        seo_result = await db.execute(
            select(func.count()).select_from(PageSEOData).where(
                PageSEOData.page_id.in_(
                    select(CrawlPage.id).where(CrawlPage.crawl_id == audit_id)
                )
            )
        )
        seo_count = seo_result.scalar_one()
        print(f"  SEO data rows:   {seo_count}")

        # ── Stage 1d: Network Data ──
        network_result = await db.execute(
            select(func.count()).select_from(PageNetworkData).where(
                PageNetworkData.page_id.in_(
                    select(CrawlPage.id).where(CrawlPage.crawl_id == audit_id)
                )
            )
        )
        network_count = network_result.scalar_one()
        print(f"  Network data:    {network_count}")

        # ── Stage 2: Parse (ParsedPageFacts) ──
        parsed_result = await db.execute(
            select(func.count()).select_from(ParsedPageFact).where(
                ParsedPageFact.audit_id == audit_id,
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
                RuleEvaluationResult.audit_id == audit_id,
            )
        )
        eval_count = eval_result.scalar_one()

        # Distinct pages evaluated
        eval_pages_result = await db.execute(
            select(func.count(func.distinct(RuleEvaluationResult.page_id))).where(
                RuleEvaluationResult.audit_id == audit_id,
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
            select(SeoAnalysisRun).where(SeoAnalysisRun.audit_id == audit_id)
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
            status_str = "[OK]" if ok else "[FAIL]"
            print(f"  {status_str} {name:<20} {detail}")
            if not ok:
                all_ok = False

        if all_ok:
            print("\n[+] Pipeline completed successfully for all stages.")
            if job and job.status != "completed":
                print(f"   [!] CrawlJob status is '{job.status}' — should be 'completed'.")
                print("      This means the analysis ran but the crawl job status was not updated.")
        else:
            print("\n[-] Pipeline did NOT complete. See [STOP] markers above for the failure point.")


async def retrigger_pipeline(audit_id: UUID):
    """Re-enqueue the analysis pipeline for a stuck audit."""
    from app.shared.tasks.celery_app import celery_app

    print("\n" + "=" * 70)
    print("RE-TRIGGERING ANALYSIS PIPELINE")
    print("=" * 70)
    print(f"  audit_id: {audit_id}")

    async with async_session_factory() as db:
        job = await db.get(CrawlJob, audit_id)
        if not job:
            print(f"\n[ERROR] CrawlJob not found for audit_id={audit_id}")
            return
        if job.status != "completed":
            print(f"\n[WARNING] CrawlJob status is '{job.status}' (not 'completed').")

    result = celery_app.send_task(
        "audit.run_analysis_pipeline",
        args=[str(audit_id)],
        queue="audit",
    )
    print(f"\n[OK] Task enqueued: audit.run_analysis_pipeline")
    print(f"     task_id: {result.id}")
    print(f"     queue:   audit")


def main():
    parser = argparse.ArgumentParser(description="Diagnose where an audit pipeline stopped.")
    parser.add_argument("--audit-id", "--crawl-id", "--project-id", dest="audit_id", type=str, required=True, help="Audit UUID")
    parser.add_argument("--retrigger", action="store_true", help="Re-enqueue the analysis pipeline if stuck")
    args = parser.parse_args()

    audit_id = UUID(args.audit_id)

    if args.retrigger:
        asyncio.run(retrigger_pipeline(audit_id))
    else:
        asyncio.run(diagnose(audit_id))


if __name__ == "__main__":
    main()
