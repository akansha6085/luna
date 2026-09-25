import pytest
from httpx import ASGITransport, AsyncClient

from luna.config import Settings
from luna.main import create_app


@pytest.fixture
def app():
    # A fresh, isolated Settings instance per test — no dependence on
    # whatever's actually in the environment / .env when tests run.
    return create_app(settings=Settings(log_level="WARNING"))


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
