"""Liveness and readiness — deliberately two different questions.

- /health (liveness): "is this process alive and not deadlocked?"
  Kubernetes uses a failing liveness probe as a signal to KILL and
  restart the pod. It should never depend on anything external — if
  Postgres is down, killing the app pod doesn't fix Postgres, it just
  adds a second outage on top of the first.

- /ready (readiness): "can this pod actually serve traffic right now?"
  Kubernetes uses a failing readiness probe to pull the pod out of the
  Service's load-balancing rotation WITHOUT killing it — the pod stays
  alive and gets traffic again the moment checks pass. This is the
  right place for "is the DB reachable" style checks.

Phase 0 has no real dependencies yet, so /ready has nothing to check —
but it's built as an extensible list of checks specifically so Phase 3
(DB) and Phase 5 (Qdrant) are additive, not a rewrite.
"""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

# Each entry: (name, async check -> True if healthy). Populated by later
# phases (e.g. db.health.check_postgres) via readiness_checks.append(...)
# from main.py's app-startup wiring — kept here as the single registry so
# /ready always reflects exactly what's actually been wired up.
readiness_checks: list[tuple[str, Callable[[], Awaitable[bool]]]] = []


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    results = {name: await check() for name, check in readiness_checks}
    all_ok = all(results.values())
    # A kubelet readinessProbe judges by HTTP status code, not body content —
    # so an unready pod MUST get a non-2xx status, or the probe silently
    # thinks everything's fine and keeps sending it traffic.
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "not_ready", "checks": results},
    )
