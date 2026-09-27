"""App factory.

`create_app()` builds and returns the FastAPI application. We use a
factory function rather than a bare module-level `app = FastAPI()`
so tests can construct fresh app instances with overridden settings
(`create_app(settings=Settings(log_level="DEBUG"))`) without import-time
side effects leaking between tests.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from luna.agents.registry import build_registry
from luna.api.routes_chat import router as chat_router
from luna.api.routes_conversations import router as conversations_router
from luna.api.routes_health import router as health_router
from luna.config import Settings, get_settings
from luna.db.base import build_engine_and_sessionmaker, check_connection
from luna.llm.groq_client import GroqClient
from luna.observability.logging import configure_logging, get_logger
from luna.observability.middleware import request_context_middleware
from luna.routing.llm_classifier import classify_with_groq
from luna.routing.router import AgentRouter

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
        groq_client = GroqClient(api_key=settings.groq_api_key)
        app.state.groq_client = groq_client
        # The registry and router both close over that one shared client
        # rather than each constructing their own — same reasoning as above.
        app.state.agent_registry = build_registry(groq_client)
        app.state.agent_router = AgentRouter(
            classify=partial(classify_with_groq, groq_client),
            confidence_threshold=settings.routing_confidence_threshold,
        )

        # The DB engine owns a real connection pool — same "build once,
        # not per-request" reasoning as the Groq client above.
        db_engine, db_sessionmaker = build_engine_and_sessionmaker(settings.database_url)
        app.state.db_engine = db_engine
        app.state.db_sessionmaker = db_sessionmaker
        # Per-app-instance list (see routes_health.py's docstring for why
        # this is NOT a module-level global) — Phase 0 built /ready as an
        # extensible registry specifically so this is additive, no rewrite.
        app.state.readiness_checks = [
            ("database", partial(check_connection, db_sessionmaker)),
        ]

        logger.info(
            "luna_startup",
            env=settings.env,
            service=settings.service_name,
            agents=list(app.state.agent_registry),
            routing_confidence_threshold=settings.routing_confidence_threshold,
        )
        yield
        # Release pooled connections explicitly rather than relying on
        # process exit to do it — matters for tests, which build many
        # short-lived app instances in one process.
        await db_engine.dispose()
        logger.info("luna_shutdown")

    app = FastAPI(title="Luna", version="0.1.0", lifespan=lifespan)

    app.middleware("http")(request_context_middleware)

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(conversations_router)

    @app.get("/")
    async def index() -> FileResponse:
        # A dev-only test page for exercising SSE streaming by eye, not a
        # real product UI. Served both from the host-run dev loop and from
        # the container image (web/ is COPYed in the Dockerfile too) so it
        # works the same way against the real deployed pod.
        return FileResponse(_WEB_DIR / "index.html")

    return app


app = create_app()
