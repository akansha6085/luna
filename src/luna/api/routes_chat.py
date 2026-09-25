"""POST /chat — multi-agent streaming chat (Phase 2: routed, still single-turn).

The core streaming mechanic is unchanged from Phase 1: an async generator
wrapped in Starlette's StreamingResponse, with two failure modes handled
explicitly because getting them wrong is the classic SSE mistake:

1. The upstream Groq call fails to start, or errors mid-stream: caught
   specifically as GroqError (never a bare `except:`), logged in full
   server-side, and surfaced to the client as an explicit `event: error`
   — so the UI can show something meaningful instead of the connection
   just going dead with no explanation.

2. The client disconnects mid-stream: Starlette cancels this generator's
   task at whatever `await`/`yield` it's paused on, which raises
   asyncio.CancelledError there. CancelledError is a BaseException, not
   an Exception, so it is NOT caught by either `except` clause below —
   it correctly skips straight to `finally` (cleanup still runs) and then
   propagates, which is what lets Starlette actually finish cancelling
   the task. Swallowing it here would be the bug.

New in Phase 2: the request is routed to one of several agents BEFORE
streaming starts (see routing/router.py), and that decision is emitted
as the first SSE event (`event: routed`) — so a UI can show something
like "answered by: coding" before the first token even arrives, and
/route-debug lets you inspect the decision without spending a full
generation call.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from luna.agents.base import Agent
from luna.api.deps import get_agent_registry, get_agent_router
from luna.api.schemas import ChatRequest
from luna.core.models import Message
from luna.llm.groq_client import GroqError
from luna.llm.streaming import sse_event
from luna.observability.logging import get_logger
from luna.routing.heuristics import RoutingDecision
from luna.routing.router import AgentRouter

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)


async def stream_chat_response(
    agent: Agent, messages: list[Message], decision: RoutingDecision
) -> AsyncIterator[str]:
    yield sse_event(
        "routed",
        {"agent": decision.agent_name, "method": decision.method, "confidence": decision.confidence},
    )

    try:
        async for chunk in agent.stream_response(messages):
            yield sse_event("token", {"text": chunk})
    except GroqError:
        logger.exception("chat_stream_upstream_error", agent=agent.name)
        yield sse_event("error", {"message": "The assistant hit an error. Please try again."})
        return
    except Exception:
        logger.exception("chat_stream_unexpected_error", agent=agent.name)
        yield sse_event("error", {"message": "Something went wrong."})
        return
    finally:
        # Guaranteed to run on normal completion, on a caught error above,
        # AND on client disconnect (CancelledError) — the one place we can
        # rely on for "the stream is over, one way or another."
        logger.info("chat_stream_closed", agent=agent.name)

    yield sse_event("done", {})


@router.post("/chat")
async def chat(
    request: ChatRequest,
    agent_router: AgentRouter = Depends(get_agent_router),
    registry: dict[str, Agent] = Depends(get_agent_registry),
) -> StreamingResponse:
    decision = await agent_router.route(request.message)
    agent = registry[decision.agent_name]
    messages = [Message(role="user", content=request.message)]
    return StreamingResponse(
        stream_chat_response(agent, messages, decision),
        media_type="text/event-stream",
    )


@router.get("/route-debug")
async def route_debug(
    message: str,
    agent_router: AgentRouter = Depends(get_agent_router),
) -> dict[str, object]:
    """Show which agent a message WOULD go to, without generating a
    response — free when the heuristic is confident, and only as
    expensive as one cheap classification call when it isn't."""
    decision = await agent_router.route(message)
    return {
        "agent": decision.agent_name,
        "method": decision.method,
        "confidence": decision.confidence,
    }
