import json
from uuid import UUID

from langchain.tools import tool

from app.modules.chat.knowledge.rule_guidance import RULE_GUIDANCE
from app.modules.chat.retrieval.category_retriever import CategoryRetriever
from app.modules.chat.retrieval.issue_retriever import IssueRetriever
from app.modules.chat.retrieval.page_retriever import PageRetriever
from sqlalchemy.ext.asyncio import AsyncSession


def build_chat_tools(db: AsyncSession, project_id: UUID) -> list:
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

        Use when the user asks about problems, errors, or issues with the site.
        Optional filters: category (e.g. 'on_page', 'technical'), rule_id, page_url.
        Returns a JSON list of issues with rule_id, severity, message, page_url, score_impact.
        """
        results = await issue_retriever.get_failed_issues(
            project_id=project_id,
            category=category,
            rule_id=rule_id,
            page_url=page_url,
            limit=limit,
        )
        return json.dumps(results, default=str)

    @tool
    async def get_category_analysis(category: str) -> str:
        """Get failed rules for a specific SEO category.

        Use when the user asks about a specific category score or category-level problems.
        Requires a category string (e.g. 'on_page', 'technical', 'content', 'links', 'images', 'schema', 'social', 'security', 'accessibility', 'performance').
        Returns a JSON list of failed rules with rule_id, severity, message, page_url, score_impact.
        """
        results = await category_retriever.get_category_failed_rules(
            project_id=project_id,
            category=category,
            limit=20,
        )
        return json.dumps(results, default=str)

    @tool
    async def get_page_facts(page_url: str) -> str:
        """Get parsed facts for a specific page URL.

        Use when the user asks about a particular page or URL.
        Requires page_url.
        Returns a JSON object with title, meta_description, canonical, headings, content word_count, technical data, and SEO data.
        Returns null if the page is not found in the audit data.
        """
        result = await page_retriever.get_page_facts(
            project_id=project_id,
            page_url=page_url,
        )
        return json.dumps(result, default=str)

    @tool
    async def get_rule_guidance(rule_id: str) -> str:
        """Get fix guidance for a specific SEO rule.

        Use when the user asks how to fix a specific issue or what a rule means.
        Requires rule_id (e.g. 'on_page_001', 'technical_001', 'images_001').
        Returns a JSON object with expected_value, where_to_fix, how_to_fix, example.
        Returns an empty JSON object if the rule is not found.
        """
        guidance = RULE_GUIDANCE.get(rule_id, {})
        return json.dumps(guidance, default=str)

    return [
        get_failed_issues,
        get_category_analysis,
        get_page_facts,
        get_rule_guidance,
    ]
