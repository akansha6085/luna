"""POST /chat — multi-agent, multi-turn, persisted streaming chat.

Phase 1 gave this one agent, no history. Phase 2 added routing. Phase 3
(this file) adds real persistence and multi-turn memory: every message
is saved to Postgres, and a conversation's prior messages are loaded and
handed to the agent as context — this is what makes a follow-up message
actually a follow-up, not an independent single-turn call answered in a
vacuum.

The streaming mechanic itself is unchanged from Phase 1/2: an async
generator wrapped in Starlette's StreamingResponse, with the same two
failure modes handled explicitly (GroqError caught specifically;
client-disconnect via CancelledError, a BaseException, correctly
skipping both `except` clauses and hitting `finally`/re-raising). New
here: `conversation` is now the FIRST SSE event (before `routed`) — a
brand-new conversation's id has to reach the client before anything
else, since every subsequent message in the thread needs it.
"""

import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from luna.agents.base import Agent
from luna.api.deps import (
    get_agent_registry,
    get_agent_router,
    get_conversation_repo,
    get_message_repo,
    get_routing_decision_repo,
)
from luna.api.schemas import ChatRequest
from luna.core.models import Message
from luna.db.repositories.conversations import ConversationRepository
from luna.db.repositories.messages import MessageRepository
from luna.db.repositories.routing_decisions import RoutingDecisionRepository
from luna.llm.groq_client import GroqError
from luna.llm.streaming import sse_event
from luna.observability.logging import get_logger
from luna.routing.heuristics import RoutingDecision
from luna.routing.router import AgentRouter

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)

_TITLE_MAX_LEN = 40


def _derive_title(message: str) -> str:
    """Same truncation convention the UI used when history lived in
    localStorage — kept identical so titles look the same either way."""
    return message if len(message) <= _TITLE_MAX_LEN else message[:_TITLE_MAX_LEN] + "…"


async def stream_chat_response(
    agent: Agent,
    messages: list[Message],
    decision: RoutingDecision,
    conversation_id: uuid.UUID,
    message_repo: MessageRepository,
    conversation_repo: ConversationRepository,
) -> AsyncIterator[str]:
    yield sse_event("conversation", {"conversation_id": str(conversation_id)})
    yield sse_event(
        "routed",
        {"agent": decision.agent_name, "method": decision.method, "confidence": decision.confidence},
    )

    full_text = ""
    finish_reason = "stop"
    start = time.perf_counter()
    try:
        async for chunk in agent.stream_response(messages):
            full_text += chunk
            yield sse_event("token", {"text": chunk})
    except GroqError:
        logger.exception("chat_stream_upstream_error", agent=agent.name)
        finish_reason = "error"
        yield sse_event("error", {"message": "The assistant hit an error. Please try again."})
    except Exception:
        logger.exception("chat_stream_unexpected_error", agent=agent.name)
        finish_reason = "error"
        yield sse_event("error", {"message": "Something went wrong."})
    finally:
        # Persist whatever text arrived, even on error/disconnect — a
        # partial answer the user can see on reload beats silently
        # losing it. Runs on normal completion, on a caught error above,
        # AND on client disconnect (CancelledError skips both `except`
        # clauses above, since it's a BaseException, and lands here).
        # Computed now and logged now, even though the DB column for it
        # is Phase 4's job (see db/models.py's Message.latency_ms) — real
        # latency visibility in structured logs shouldn't wait on that.
        latency_ms = round((time.perf_counter() - start) * 1000)
        if full_text:
            await message_repo.add(
                conversation_id,
                role="assistant",
                content=full_text,
                agent_name=agent.name,
                finish_reason=finish_reason,
            )
            await conversation_repo.touch(conversation_id)
        logger.info(
            "chat_stream_closed", agent=agent.name, finish_reason=finish_reason, latency_ms=latency_ms
        )

    if finish_reason == "stop":
        yield sse_event("done", {})


@router.post("/chat")
async def chat(
    request: ChatRequest,
    agent_router: AgentRouter = Depends(get_agent_router),
    registry: dict[str, Agent] = Depends(get_agent_registry),
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    routing_decision_repo: RoutingDecisionRepository = Depends(get_routing_decision_repo),
) -> StreamingResponse:
    if request.conversation_id is None:
        conversation = await conversation_repo.create()
        history: list[Message] = []
    else:
        # A separate `fetched` (typed Conversation | None) rather than
        # reassigning `conversation` directly: mypy infers a bare
        # variable's type from its first assignment above (Conversation,
        # non-optional) and flags reassigning an Optional to it as
        # incompatible — even though it IS narrowed to non-None by the
        # time it's used, two lines down. Narrowing `fetched` here and
        # assigning the narrowed value avoids the false positive cleanly.
        fetched = await conversation_repo.get(request.conversation_id)
        if fetched is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        conversation = fetched
        history = await message_repo.list_as_core_messages(conversation.id)

    await conversation_repo.set_title_if_unset(conversation.id, _derive_title(request.message))

    # Persisted BEFORE the Groq call starts — durability: a crash mid-
    # generation still leaves the user's own message safely saved.
    user_message = await message_repo.add(conversation.id, role="user", content=request.message)

    decision = await agent_router.route(request.message)
    await routing_decision_repo.record(user_message.id, decision)
    agent = registry[decision.agent_name]

    # Prior turns + this one — the actual multi-turn memory. Phase 1/2's
    # /chat only ever sent a single message; this is the whole point of
    # Phase 3's persistence existing.
    messages = [*history, Message(role="user", content=request.message)]

    return StreamingResponse(
        stream_chat_response(
            agent, messages, decision, conversation.id, message_repo, conversation_repo
        ),
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
