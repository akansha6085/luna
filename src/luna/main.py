"""App factory.

`create_app()` builds and returns the FastAPI application. We use a
factory function rather than a bare module-level `app = FastAPI()`
so tests can construct fresh app instances with overridden settings
(`create_app(settings=Settings(log_level="DEBUG"))`) without import-time
side effects leaking between tests.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from luna.api.routes_health import router as health_router
from luna.config import Settings, get_settings
from luna.observability.logging import configure_logging, get_logger
from luna.observability.middleware import request_context_middleware

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("luna_startup", env=settings.env, service=settings.service_name)
        yield
        logger.info("luna_shutdown")

    app = FastAPI(title="Luna", version="0.1.0", lifespan=lifespan)

    app.middleware("http")(request_context_middleware)

    app.include_router(health_router)

    return app


app = create_app()
