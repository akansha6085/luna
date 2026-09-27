"""FastAPI dependency-injection providers.

Every external dependency (settings, the shared Groq client, the agent
registry, the router, a DB session) is obtained via `Depends(...)` in
route handlers — never constructed inline in a handler body. This is the
one seam tests substitute fakes at, and the reason routing/heuristics and
the SSE generator itself can be unit-tested with zero network calls (see
tests/unit/).

The GroqClient, agent registry, router, and DB sessionmaker are NOT
constructed here per-request — they're built once in main.py's lifespan
(the registry and router both close over the one shared GroqClient) and
stashed on `app.state`. Most getters here just read them back out; the
one exception is get_db_session, which DOES create something
per-request (an AsyncSession) — see its docstring for why that's correct.
"""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from luna.agents.base import Agent
from luna.db.repositories.conversations import ConversationRepository
from luna.db.repositories.messages import MessageRepository
from luna.db.repositories.routing_decisions import RoutingDecisionRepository
from luna.llm.groq_client import GroqClient
from luna.routing.router import AgentRouter


def get_groq_client(request: Request) -> GroqClient:
    client: GroqClient = request.app.state.groq_client
    return client


def get_agent_registry(request: Request) -> dict[str, Agent]:
    registry: dict[str, Agent] = request.app.state.agent_registry
    return registry


def get_agent_router(request: Request) -> AgentRouter:
    router: AgentRouter = request.app.state.agent_router
    return router


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A fresh AsyncSession per request — NOT built at startup, unlike
    everything above. The engine/pool is the long-lived resource (built
    once in main.py's lifespan); a Session is a lightweight, short-lived
    unit-of-work that should NOT be shared across requests or held open
    longer than one.

    FastAPI caches a dependency's result per-request, so every
    Depends(get_db_session) call within the SAME request (e.g. across
    get_conversation_repo, get_message_repo, get_routing_decision_repo
    below) resolves to this one session — they share a transaction
    scope without any explicit wiring.
    """
    session_factory = request.app.state.db_sessionmaker
    async with session_factory() as session:
        yield session


def get_conversation_repo(
    session: AsyncSession = Depends(get_db_session),
) -> ConversationRepository:
    return ConversationRepository(session)


def get_message_repo(session: AsyncSession = Depends(get_db_session)) -> MessageRepository:
    return MessageRepository(session)


def get_routing_decision_repo(
    session: AsyncSession = Depends(get_db_session),
) -> RoutingDecisionRepository:
    return RoutingDecisionRepository(session)
