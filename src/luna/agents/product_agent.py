from luna.agents.base import SimpleAgent


class ProductAgent(SimpleAgent):
    name = "product"
    system_prompt = (
        "You are Luna's product specialist. Help with product strategy, feature "
        "requests, requirements, user experience, and roadmap questions. Be "
        "clear about tradeoffs."
    )
    model = "openai/gpt-oss-20b"
