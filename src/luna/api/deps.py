"""FastAPI dependency-injection providers.

Every external dependency (settings, the shared Groq client, the agent
registry, the router) is obtained via `Depends(...)` in route handlers —
never constructed inline in a handler body. This is the one seam tests
substitute fakes at, and the reason routing/heuristics and the SSE
generator itself can be unit-tested with zero network calls (see
tests/unit/).

The GroqClient, agent registry, and router are NOT constructed here
per-request — they're built once in main.py's lifespan (the registry and
router both close over the one shared GroqClient) and stashed on
`app.state`. These getters just read them back out.
"""

from fastapi import Request

from luna.agents.base import Agent
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
