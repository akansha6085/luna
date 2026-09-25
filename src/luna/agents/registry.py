"""The static, explicit agent registry — the Strategy pattern's dispatch table.

Adding a new agent later means: write one new small file (see
coding_agent.py for the template) + add one line here. Nothing in
routing/ or api/ has to change — that's the concrete proof of the
open-closed principle, not just an abstract claim about it.

Deliberately a plain dict built once at startup, not a database table —
see the project plan's data-model notes for why (keeps the pattern
concrete; a DB-backed dynamic registry would be a reasonable *future*
extension, not needed to teach this).
"""

from luna.agents.assistant_agent import AssistantAgent
from luna.agents.base import Agent
from luna.agents.coding_agent import CodingAgent
from luna.agents.infra_agent import InfraAgent
from luna.agents.product_agent import ProductAgent
from luna.llm.groq_client import GroqClient


def build_registry(groq_client: GroqClient) -> dict[str, Agent]:
    agents: list[Agent] = [
        AssistantAgent(groq_client),
        CodingAgent(groq_client),
        InfraAgent(groq_client),
        ProductAgent(groq_client),
    ]
    return {agent.name: agent for agent in agents}
