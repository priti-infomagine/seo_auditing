"""restructure_crawler_models_to_6_aggregates

Revision ID: d1e2f3a4b5c6
Revises: c1a2b3c4d5e6
Create Date: 2026-08-10 11:34:00.000000

"""
from typing import Sequence, Union
import hashlib

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Add new columns to crawl_jobs ─────────────────────────────────
    op.add_column("crawl_jobs", sa.Column("project_id", sa.UUID(), nullable=True))
    op.add_column("crawl_jobs", sa.Column("crawl_type", sa.String(length=50), nullable=True))
    op.add_column("crawl_jobs", sa.Column("pages_discovered", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("pages_crawled", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("pages_failed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("crawl_config", sa.JSON(), nullable=True))

    # ── 2. Migrate crawl_configs data into crawl_jobs.crawl_config JSONB ─
    op.execute("""
        UPDATE crawl_jobs
        SET crawl_config = jsonb_build_object(
            'max_depth', cc.max_depth,
            'max_pages', cc.max_pages,
            'concurrency', cc.concurrency,
            'request_timeout', cc.timeout_seconds,
            'delay_ms', cc.delay_ms,
            'follow_redirects', cc.follow_redirects,
            'respect_robots', cc.respect_robots,
            'user_agent', cc.user_agent
        )
        FROM crawl_configs cc
        WHERE crawl_jobs.id = cc.crawl_id
    """)

    # ── 3. Drop crawl_configs table ──────────────────────────────────────
    op.drop_index(op.f("ix_crawl_configs_crawl_id"), table_name="crawl_configs")
    op.drop_table("crawl_configs")

    # ── 4. Add new columns to crawl_pages ────────────────────────────────
    op.add_column("crawl_pages", sa.Column("url_hash", sa.String(length=64), nullable=False))
    op.add_column("crawl_pages", sa.Column("scheme", sa.String(length=10), nullable=True))
    op.add_column("crawl_pages", sa.Column("host", sa.String(length=255), nullable=True))
    op.add_column("crawl_pages", sa.Column("path", sa.Text(), nullable=True))
    op.add_column("crawl_pages", sa.Column("query", sa.Text(), nullable=True))
    op.add_column("crawl_pages", sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("crawl_pages", sa.Column("is_crawled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("crawl_pages", sa.Column("is_success", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("crawl_pages", sa.Column("is_redirect", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("crawl_pages", sa.Column("is_error", sa.Boolean(), nullable=False, server_default="false"))

    # Create index on url_hash
    op.create_index(op.f("ix_crawl_pages_url_hash"), "crawl_pages", ["url_hash"], unique=False)
    op.create_index(op.f("ix_crawl_pages_host"), "crawl_pages", ["host"], unique=False)

    # ── 5. Backfill crawl_pages URL decomposition fields ─────────────────
    op.execute("""
        UPDATE crawl_pages
        SET
            url_hash = encode(sha256(normalized_url::bytea), 'hex'),
            scheme = split_part(url, '://', 1),
            host = split_part(split_part(url, '://', 2), '/', 1),
            path = CASE
                WHEN position('/' in split_part(url, '://', 2)) > 0
                THEN '/' || regexp_replace(split_part(url, '://', 2), '^[^/]+', '')
                ELSE '/'
            END,
            query = CASE
                WHEN position('?' in url) > 0
                THEN substr(url, position('?' in url) + 1)
                ELSE NULL
            END,
            is_internal = true,
            is_crawled = crawled_at IS NOT NULL,
            is_success = status_code >= 200 AND status_code < 400,
            is_redirect = status_code >= 300 AND status_code < 400,
            is_error = status_code >= 400 OR status_code IS NULL
    """)

    # ── 6. Add new columns to page_links ─────────────────────────────────
    op.add_column("page_links", sa.Column("crawl_job_id", sa.UUID(), nullable=False, server_default="00000000-0000-0000-0000-000000000000"))
    op.add_column("page_links", sa.Column("normalized_target_url", sa.Text(), nullable=True))
    op.add_column("page_links", sa.Column("is_external", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("page_links", sa.Column("nofollow", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("page_links", sa.Column("ugc", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("page_links", sa.Column("sponsored", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("page_links", sa.Column("is_crawlable", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("page_links", sa.Column("target_status_code", sa.Integer(), nullable=True))
    op.add_column("page_links", sa.Column("target_response_time_ms", sa.Integer(), nullable=True))
    op.add_column("page_links", sa.Column("target_error", sa.Text(), nullable=True))

    # Create index on crawl_job_id
    op.create_index(op.f("ix_page_links_crawl_job_id"), "page_links", ["crawl_job_id"], unique=False)

    # ── 7. Backfill page_links crawl_job_id and normalized_target_url ────
    op.execute("""
        UPDATE page_links
        SET
            crawl_job_id = (SELECT crawl_id FROM crawl_pages WHERE crawl_pages.id = page_links.page_id),
            normalized_target_url = target_url,
            is_external = NOT is_internal
        WHERE crawl_job_id = '00000000-0000-0000-0000-000000000000'
    """)

    # Remove server_default after backfill
    op.alter_column("page_links", "crawl_job_id", server_default=None)

    # ── 8. Create new tables ─────────────────────────────────────────────
    op.create_table(
        "page_seo_data",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("title_length", sa.Integer(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("meta_description_length", sa.Integer(), nullable=True),
        sa.Column("canonical", sa.Text(), nullable=True),
        sa.Column("robots_meta", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("charset", sa.String(length=50), nullable=True),
        sa.Column("viewport", sa.Text(), nullable=True),
        sa.Column("favicon", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("headings", sa.JSON(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("structured_data", sa.JSON(), nullable=True),
        sa.Column("social", sa.JSON(), nullable=True),
        sa.Column("indexability", sa.JSON(), nullable=True),
        sa.Column("accessibility", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["crawl_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_page_seo_data_page_id"), "page_seo_data", ["page_id"], unique=True)

    op.create_table(
        "page_resources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("alt", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("loading", sa.String(length=20), nullable=True),
        sa.Column("srcset", sa.Text(), nullable=True),
        sa.Column("sizes", sa.Text(), nullable=True),
        sa.Column("is_lazy", sa.Boolean(), nullable=True),
        sa.Column("is_mixed_content", sa.Boolean(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["crawl_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_page_resources_page_id"), "page_resources", ["page_id"], unique=False)

    op.create_table(
        "page_network_data",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("redirects", sa.JSON(), nullable=True),
        sa.Column("security", sa.JSON(), nullable=True),
        sa.Column("performance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["crawl_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_page_network_data_page_id"), "page_network_data", ["page_id"], unique=True)

    op.create_table(
        "crawl_site_data",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("crawl_job_id", sa.UUID(), nullable=False),
        sa.Column("robots", sa.JSON(), nullable=True),
        sa.Column("sitemaps", sa.JSON(), nullable=True),
        sa.Column("statistics", sa.JSON(), nullable=True),
        sa.Column("duplicate_clusters", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["crawl_job_id"], ["crawl_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_site_data_crawl_job_id"), "crawl_site_data", ["crawl_job_id"], unique=True)


def downgrade() -> None:
    # ── Drop new tables ──────────────────────────────────────────────────
    op.drop_index(op.f("ix_crawl_site_data_crawl_job_id"), table_name="crawl_site_data")
    op.drop_table("crawl_site_data")
    op.drop_index(op.f("ix_page_network_data_page_id"), table_name="page_network_data")
    op.drop_table("page_network_data")
    op.drop_index(op.f("ix_page_resources_page_id"), table_name="page_resources")
    op.drop_table("page_resources")
    op.drop_index(op.f("ix_page_seo_data_page_id"), table_name="page_seo_data")
    op.drop_table("page_seo_data")

    # ── Recreate crawl_configs table ────────────────────────────────────
    op.create_table(
        "crawl_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("crawl_id", sa.UUID(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("delay_ms", sa.Integer(), nullable=False),
        sa.Column("follow_redirects", sa.Boolean(), nullable=False),
        sa.Column("respect_robots", sa.Boolean(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["crawl_id"], ["crawl_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_configs_crawl_id"), "crawl_configs", ["crawl_id"], unique=False)

    # ── Remove new columns from crawl_jobs ──────────────────────────────
    op.drop_column("crawl_jobs", "crawl_config")
    op.drop_column("crawl_jobs", "error_count")
    op.drop_column("crawl_jobs", "pages_failed")
    op.drop_column("crawl_jobs", "pages_crawled")
    op.drop_column("crawl_jobs", "pages_discovered")
    op.drop_column("crawl_jobs", "crawl_type")
    op.drop_column("crawl_jobs", "project_id")

    # ── Remove new columns from crawl_pages ─────────────────────────────
    op.drop_index(op.f("ix_crawl_pages_host"), table_name="crawl_pages")
    op.drop_index(op.f("ix_crawl_pages_url_hash"), table_name="crawl_pages")
    op.drop_column("crawl_pages", "is_error")
    op.drop_column("crawl_pages", "is_redirect")
    op.drop_column("crawl_pages", "is_success")
    op.drop_column("crawl_pages", "is_crawled")
    op.drop_column("crawl_pages", "is_internal")
    op.drop_column("crawl_pages", "query")
    op.drop_column("crawl_pages", "path")
    op.drop_column("crawl_pages", "host")
    op.drop_column("crawl_pages", "scheme")
    op.drop_column("crawl_pages", "url_hash")

    # ── Remove new columns from page_links ──────────────────────────────
    op.drop_index(op.f("ix_page_links_crawl_job_id"), table_name="page_links")
    op.drop_column("page_links", "target_error")
    op.drop_column("page_links", "target_response_time_ms")
    op.drop_column("page_links", "target_status_code")
    op.drop_column("page_links", "is_crawlable")
    op.drop_column("page_links", "sponsored")
    op.drop_column("page_links", "ugc")
    op.drop_column("page_links", "nofollow")
    op.drop_column("page_links", "is_external")
    op.drop_column("page_links", "normalized_target_url")
    op.drop_column("page_links", "crawl_job_id")
