"""Alembic environment — async variant.

The standard `alembic init` template is sync (`engine_from_config` +
plain `engine.connect()`), which won't work with an asyncpg-based async
engine. This follows Alembic's own documented async pattern: build an
AsyncEngine, then use `connection.run_sync(...)` to bridge into Alembic's
still-synchronous migration-running internals.

The connection string comes from `luna.config.Settings` — the same
single source of truth the app itself uses — rather than a second copy
of it living in alembic.ini.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from luna.config import get_settings
from luna.db import models  # noqa: F401 -- import registers ORM classes on Base.metadata
from luna.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — emits SQL without a live DB connection."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    # NullPool: this engine exists for the lifetime of one `alembic`
    # invocation, not a long-running server — no connection pool to
    # maintain, no benefit to pooling here.
    connectable = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
