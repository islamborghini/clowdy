"""
Alembic migration environment.

Configures Alembic to work with our async SQLAlchemy engine.
Alembic uses this file to know how to connect to the database
and which models to compare against when generating migrations.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import DATABASE_URL
from app.models import Base

config = context.config

# Override the sqlalchemy.url from alembic.ini with our app's config
# so we have a single source of truth for the database URL.
# Strip the async driver prefix since Alembic runs synchronously.
_sync_url = DATABASE_URL.replace("+aiosqlite", "")
config.set_main_option("sqlalchemy.url", _sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the MetaData object from our models. Alembic compares this
# against the actual database schema to generate migrations.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live database connection (generates SQL only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a sync database connection.

    Uses a plain synchronous engine since Alembic is synchronous.
    This avoids issues with asyncio.run() failing when called from
    within FastAPI's already-running async event loop.
    """
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
