"""FastAPI dependency-injection providers.

Every external dependency (settings, the shared Groq client, an agent)
is obtained via `Depends(...)` in route handlers — never constructed
inline in a handler body. This is the one seam tests substitute fakes
at, and the reason routing/heuristics and the SSE generator itself can
be unit-tested with zero network calls (see tests/unit/).

The GroqClient itself is NOT constructed here per-request — it holds a
real HTTP connection pool, so it's built once in main.py's lifespan and
stashed on `app.state`. get_groq_client just reads it back out.
"""

from fastapi import Depends, Request

from luna.agents.assistant_agent import AssistantAgent
from luna.llm.groq_client import GroqClient


def get_groq_client(request: Request) -> GroqClient:
    client: GroqClient = request.app.state.groq_client
    return client


def get_assistant_agent(groq_client: GroqClient = Depends(get_groq_client)) -> AssistantAgent:
    return AssistantAgent(groq_client=groq_client)
