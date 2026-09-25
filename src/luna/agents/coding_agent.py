from luna.agents.base import SimpleAgent


class CodingAgent(SimpleAgent):
    name = "coding"
    system_prompt = (
        "You are Luna's coding specialist. Help with code, bugs, algorithms, "
        "debugging, and software-design questions. Be precise, and include short "
        "code snippets when they clarify the answer."
    )
    model = "openai/gpt-oss-20b"
