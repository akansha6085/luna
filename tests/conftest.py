import pytest
from httpx import ASGITransport, AsyncClient

from luna.config import Settings
from luna.main import create_app


@pytest.fixture
def app():
    # A fresh, isolated Settings instance per test — no dependence on
    # whatever's actually in the environment / .env when tests run, and
    # never a real secret in a test. The database_url deliberately points
    # nowhere reachable (port 1 is essentially guaranteed refused
    # instantly) — unit tests touch zero external services, including
    # Postgres; see test_ready_reports_database_check_from_lifespan for
    # the one test that explicitly relies on that failure.
    return create_app(
        settings=Settings(
            log_level="WARNING",
            groq_api_key="test-key",
            database_url="postgresql+asyncpg://test:test@127.0.0.1:1/test",
        )
    )


@pytest.fixture
async def client(app):
    # Plain ASGITransport does NOT run the app's lifespan (that's what
    # populates app.state.agent_registry/agent_router in main.py) — only
    # FastAPI's own TestClient does that automatically. Driving
    # `app.router.lifespan_context` explicitly is the equivalent for a
    # raw httpx.AsyncClient, and is what makes routes that depend on
    # app.state actually work in tests.
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
