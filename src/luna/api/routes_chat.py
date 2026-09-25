"""POST /chat — single-agent streaming chat (Phase 1: stateless, single-turn).

The core mechanic is an async generator wrapped in Starlette's
StreamingResponse. Two failure modes get explicit handling, because
getting them wrong is the classic SSE mistake:

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
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from luna.agents.base import Agent
from luna.api.deps import get_assistant_agent
from luna.api.schemas import ChatRequest
from luna.core.models import Message
from luna.llm.groq_client import GroqError
from luna.llm.streaming import sse_event
from luna.observability.logging import get_logger

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)


async def stream_chat_response(agent: Agent, messages: list[Message]) -> AsyncIterator[str]:
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
    agent: Agent = Depends(get_assistant_agent),
) -> StreamingResponse:
    messages = [Message(role="user", content=request.message)]
    return StreamingResponse(
        stream_chat_response(agent, messages),
        media_type="text/event-stream",
    )
