"""ASGI middleware: request-id tagging + basic access logging.

Every request gets a request-id (reused from an inbound `X-Request-ID`
header if the caller sent one, otherwise generated). It's:

- bound into structlog's contextvars, so every log line emitted anywhere
  during this request automatically carries it, with zero effort from
  the code that logs;
- echoed back as a response header, so a caller (or, later, a human
  correlating a browser error with server logs) can tie the two together.

This is what turns "search Loki for errors" (Phase 6) into "search Loki
for this exact request" — the plumbing has to exist before the request
happens, so it goes in now even though there's nothing interesting to
correlate yet.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

logger = structlog.get_logger("luna.access")

REQUEST_ID_HEADER = "X-Request-ID"


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception("request_failed", duration_ms=duration_ms)
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers[REQUEST_ID_HEADER] = request_id
    logger.info(
        "request_completed",
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response
