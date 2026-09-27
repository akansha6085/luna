"""Integration test fixtures — require a REAL Postgres (the same one
`docker-compose.dev.yml` starts for local dev): `make compose-up` first,
then `make test-integration`. Deliberately not sqlite and not a mock —
sqlite would give a false sense of safety by testing against a
different engine than what's actually deployed.

Uses a separate `luna_test` database (created here if it doesn't exist)
rather than the same `luna` database manual dev work happens in, so
running tests never touches or clobbers real dev conversations.
"""

from collections.abc import AsyncIterator

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from luna.config import get_settings
from luna.db.base import Base, build_engine_and_sessionmaker


def _test_database_url() -> str:
    base = get_settings().database_url
    return base.rsplit("/", 1)[0] + "/luna_test"


def _admin_url_for_asyncpg() -> str:
    # asyncpg.connect() wants a plain postgresql:// URL (no +asyncpg
    # driver suffix — that's a SQLAlchemy-ism), pointed at the "postgres"
    # maintenance database: CREATE DATABASE cannot run inside another
    # database's own transaction/connection.
    base = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    return base.rsplit("/", 1)[0] + "/postgres"


async def _ensure_test_database_exists() -> None:
    conn = await asyncpg.connect(_admin_url_for_asyncpg())
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'luna_test'")
        if not exists:
            await conn.execute("CREATE DATABASE luna_test")
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def _test_schema() -> AsyncIterator[None]:
    await _ensure_test_database_exists()
    engine, _ = build_engine_and_sessionmaker(_test_database_url())
    async with engine.begin() as conn:
        # create_all (not Alembic) is deliberate HERE: an ephemeral test
        # schema, recreated fresh every run, is a different concern from
        # production schema changes — those always go through Alembic
        # (see migrations/). Using create_all for tests isn't a shortcut
        # around that discipline, it's a genuinely different use case.
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine, session_factory = build_engine_and_sessionmaker(_test_database_url())
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    # Truncate everything after each test rather than dropping/recreating
    # the schema — cheaper, and Base.metadata.sorted_tables is already in
    # FK-dependency order; reversed deletes children before parents.
    for table in reversed(Base.metadata.sorted_tables):
        await db_session.execute(table.delete())
    await db_session.commit()
