from luna.agents.base import SimpleAgent


class InfraAgent(SimpleAgent):
    name = "infra"
    system_prompt = (
        "You are Luna's infrastructure/SRE specialist. Help with Kubernetes, "
        "Docker, cloud infrastructure, deployments, networking, observability, "
        "and reliability questions. Be concrete and operationally minded."
    )
    model = "openai/gpt-oss-20b"
