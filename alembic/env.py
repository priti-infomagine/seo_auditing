from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config object
config = context.config

# Set up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.core.database import Base
from app.core.config import settings

# ============================================================
# IMPORT ALL MODEL MODULES BEFORE target_metadata
# ============================================================

# Auth
import app.modules.auth.models  # noqa: F401

# Crawler
import app.modules.crawler.models  # noqa: F401

# Reports
import app.modules.reports.models  # noqa: F401

# Payments
import app.modules.payment.models  # noqa: F401

# Robots
import app.modules.seprate_checks.robots_check.model  # noqa: F401

# Audit
import app.modules.audit.models.parsed_page_facts  # noqa: F401
import app.modules.audit.models.rule_evaluation_results  # noqa: F401
import app.modules.audit.models.seo_analysis_runs  # noqa: F401
# Lighthouse
import app.modules.seprate_checks.google_lighthouse_check.model  # noqa: F401

# Config
import app.modules.config.models  # noqa: F401

# IMPORTANT: set this AFTER all models are imported
target_metadata = Base.metadata

target_metadata = Base.metadata
print("\n=== REGISTERED SQLALCHEMY TABLES ===")
for table_name in sorted(Base.metadata.tables.keys()):
    print(table_name)



print(f"\nTOTAL TABLES: {len(Base.metadata.tables)}")
print("====================================\n")

# Override sqlalchemy.url with our sync URL from settings
sync_url = settings.sync_database_url
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a synchronous engine."""
    from sqlalchemy import create_engine

    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()