"""App factory.

`create_app()` builds and returns the FastAPI application. We use a
factory function rather than a bare module-level `app = FastAPI()`
so tests can construct fresh app instances with overridden settings
(`create_app(settings=Settings(log_level="DEBUG"))`) without import-time
side effects leaking between tests.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from luna.api.routes_chat import router as chat_router
from luna.api.routes_health import router as health_router
from luna.config import Settings, get_settings
from luna.llm.groq_client import GroqClient
from luna.observability.logging import configure_logging, get_logger
from luna.observability.middleware import request_context_middleware

_WEB_DIR = Path(__file__).resolve().parents[2] / "web"

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The Groq client holds a real HTTP connection pool — build it
        # once here, not per-request (see api/deps.py), and stash it on
        # app.state so route dependencies can read it back out.
        app.state.groq_client = GroqClient(api_key=settings.groq_api_key)
        logger.info("luna_startup", env=settings.env, service=settings.service_name)
        yield
        logger.info("luna_shutdown")

    app = FastAPI(title="Luna", version="0.1.0", lifespan=lifespan)

    app.middleware("http")(request_context_middleware)

    app.include_router(health_router)
    app.include_router(chat_router)

    @app.get("/")
    async def index() -> FileResponse:
        # A dev-only test page for exercising SSE streaming by eye, not a
        # real product UI. Served both from the host-run dev loop and from
        # the container image (web/ is COPYed in the Dockerfile too) so it
        # works the same way against the real deployed pod.
        return FileResponse(_WEB_DIR / "index.html")

    return app


app = create_app()
