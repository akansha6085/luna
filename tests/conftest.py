import pytest
from httpx import ASGITransport, AsyncClient

from luna.config import Settings
from luna.main import create_app


@pytest.fixture
def app():
    # A fresh, isolated Settings instance per test — no dependence on
    # whatever's actually in the environment / .env when tests run, and
    # never a real secret in a test.
    return create_app(settings=Settings(log_level="WARNING", groq_api_key="test-key"))


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
