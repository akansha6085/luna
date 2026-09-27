"""Async engine + session factory.

Async, not sync — deliberately. A sync SQLAlchemy engine would block the
event loop on every query, which would silently defeat the whole point
of the async architecture built in Phases 1-2 (the app could no longer
serve a second request while one is waiting on the DB). This is also
why "just use sync SQLAlchemy to get it working" (a common shortcut in
tutorials) would mean a rewrite later, not just a swap.

The engine is built ONCE at startup (main.py's lifespan) and stashed on
app.state, exactly like the GroqClient — it owns a real connection pool.
Individual request handlers get a fresh AsyncSession per request via
api/deps.py's get_db_session, not the engine itself.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base — every ORM model in db/models.py inherits
    this. Alembic's migrations/env.py imports Base.metadata to
    autogenerate schema diffs against."""


def build_engine_and_sessionmaker(
    database_url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        database_url,
        # Checks a pooled connection is actually alive before handing it
        # out, re-connecting if not. Cheap insurance against "the DB
        # restarted / the connection went stale" errors that would
        # otherwise surface as a confusing failure on an unrelated request.
        pool_pre_ping=True,
    )
    # expire_on_commit=False: without this, SQLAlchemy expires all
    # attributes on commit, and the NEXT attribute access re-triggers a
    # lazy load — which fails outside an active async context unless
    # awaited carefully. Since we often want to read back what we just
    # wrote (e.g. a message's generated id/created_at right after
    # inserting it) within the same request, this is the standard async
    # SQLAlchemy setting to avoid that trap.
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


async def check_connection(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """The DB readiness check registered into `app.state.readiness_checks`
    in main.py's lifespan (see api/routes_health.py's /ready). A plain
    `SELECT 1` — deliberately not schema-specific, so it stays valid
    across every future migration."""
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 -- a health check's whole job is to
        # catch ANYTHING that means "can't reach the DB right now" (auth
        # failure, network drop, DNS not resolved yet on pod startup...)
        # and report unhealthy, never to crash /ready itself.
        return False
