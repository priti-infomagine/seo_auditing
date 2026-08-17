import asyncio
from uuid import uuid4, UUID

from app.core.database import async_session_factory
from app.modules.audit.models.parsed_page_facts import ParsedPageFact
from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult
from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.rule_engine.models.rule_result import Severity


async def test_models():
    test_project_id = uuid4()
    test_crawl_id = uuid4()
    test_page_id = uuid4()

    async with async_session_factory() as db:
        # Test ParsedPageFact
        fact_repo = ParsedPageFactRepository(db)
        
        fact = ParsedPageFact(
            project_id=test_project_id,
            crawl_id=test_crawl_id,
            page_id=test_page_id,
            url="https://example.com/page1",
            domain="example.com",
            parsed_data={"content": {"text": "hello"}, "headings": []},
            page_facts={"title": "Test Page", "word_count": 42},
            elements={"headings": []},
            attributes={"links": []},
            content_hash="abc123",
        )
        await fact_repo.upsert(fact)
        await fact_repo.upsert(fact)  # idempotent
        
        retrieved = await fact_repo.get_by_page_id(test_project_id, test_page_id)
        assert retrieved is not None
        assert retrieved.url == "https://example.com/page1"
        assert retrieved.page_facts["title"] == "Test Page"
        print("ParsedPageFact: upsert + query OK")
        
        assert await fact_repo.exists(test_project_id, test_page_id)
        print("ParsedPageFact: exists OK")

        # Test RuleEvaluationResult
        rule_repo = RuleEvaluationResultRepository(db)
        
        result = RuleEvaluationResult(
            project_id=test_project_id,
            crawl_id=test_crawl_id,
            page_id=test_page_id,
            rule_id="title_tag",
            rule_name="Title Tag",
            category="on_page",
            severity=Severity.CRITICAL.value,
            passed=False,
            score_impact=-10,
            message="Title tag is missing",
            recommendation="Add a title tag",
            rule_data={"expected": 50, "actual": 0},
            tags=["seo", "on_page"],
        )
        await rule_repo.upsert(result)
        await rule_repo.upsert(result)  # idempotent
        
        results = await rule_repo.get_by_page_id(test_project_id, test_page_id)
        assert len(results) == 1
        assert results[0].rule_id == "title_tag"
        assert results[0].passed == False
        print("RuleEvaluationResult: upsert + query OK")
        
        summary = await rule_repo.get_summary(test_project_id)
        assert summary["total"] == 1
        assert summary["failed"] == 1
        print("RuleEvaluationResult: summary OK")

        # Test SeoAnalysisRun
        analysis_repo = SeoAnalysisRunRepository(db)
        
        run = SeoAnalysisRun(
            project_id=test_project_id,
            crawl_id=test_crawl_id,
            domain="example.com",
            overall_score=75.5,
            grade="C",
            total_pages_scored=1,
            total_rules_evaluated=1,
            total_passed=0,
            total_failed=1,
            critical_issues=1,
            warnings=0,
            error_pages=0,
            category_scores={"on_page": {"score": 75.0}},
            top_issues=[],
            summary="Test summary",
            output_file_path="/app/output/example.com_abc.json",
            analysis_status="completed",
        )
        await analysis_repo.upsert(run)
        await analysis_repo.upsert(run)  # idempotent
        
        retrieved_run = await analysis_repo.get_by_project_id(test_project_id)
        assert retrieved_run is not None
        assert retrieved_run.overall_score == 75.5
        assert retrieved_run.grade == "C"
        assert retrieved_run.analysis_status == "completed"
        print("SeoAnalysisRun: upsert + query OK")

        # Clean up
        await fact_repo.delete_by_project_id(test_project_id)
        await rule_repo.delete_by_project_id(test_project_id)
        await analysis_repo.delete_by_project_id(test_project_id)
        await db.commit()
        print("\nAll model/repository tests PASSED!")


asyncio.run(test_models())
