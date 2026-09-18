import json
import re
import time
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chat.knowledge.rule_guidance import RULE_GUIDANCE
from app.modules.chat.retrieval.category_retriever import CategoryRetriever
from app.modules.chat.retrieval.issue_retriever import IssueRetriever
from app.modules.chat.retrieval.page_retriever import PageRetriever


def build_chat_tools(
    db: AsyncSession,
    audit_id: UUID,
) -> list:
    issue_retriever = IssueRetriever(db)
    category_retriever = CategoryRetriever(db)
    page_retriever = PageRetriever(db)

    @tool
    async def get_failed_issues(
        category: str | None = None,
        rule_id: str | None = None,
        page_url: str | None = None,
        limit: int = 10,
    ) -> str:
        """Retrieve failed SEO audit issues.

        Use for site problems, errors, or SEO issues.
        Filters: category, rule_id, page_url.
        """

        limit = min(max(limit, 1), 20)

        results = await issue_retriever.get_failed_issues(
            audit_id=audit_id,
            category=category,
            rule_id=rule_id,
            page_url=page_url,
            limit=limit,
        )

        return json.dumps(results, default=str)

    @tool
    async def get_category_analysis(category: str) -> str:
        """Get failed SEO rules for one category.

        Valid categories include:
        on_page, technical, content, links, images, schema,
        social, security, accessibility, performance.
        """

        results = await category_retriever.get_category_failed_rules(
            audit_id=audit_id,
            category=category,
            limit=20,
        )

        return json.dumps(results, default=str)

    @tool
    async def get_page_facts(page_url: str) -> str:
        """Get parsed SEO facts for one page URL."""

        start = time.perf_counter()

        page_url = page_url.strip()

        # Convert Markdown link to plain URL.
        markdown_match = re.fullmatch(
            r"\[([^\]]+)\]\(([^)]+)\)",
            page_url,
        )

        if markdown_match:
            page_url = markdown_match.group(2).strip()

        result = await page_retriever.get_page_facts(
            audit_id=audit_id,
            page_url=page_url,
        )

        elapsed = time.perf_counter() - start
        print(f"get_page_facts completed in {elapsed:.2f}s")

        return json.dumps(result, default=str)

    @tool
    async def get_rule_guidance(rule_id: str) -> str:
        """Get fix guidance for an SEO rule."""

        guidance = RULE_GUIDANCE.get(rule_id.strip(), {})
        return json.dumps(guidance, default=str)

    return [
        get_failed_issues,
        get_category_analysis,
        get_page_facts,
        get_rule_guidance,
    ]