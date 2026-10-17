"""A small Strands agent hosted on AgentCore Runtime (fixture; never executed)."""

from bedrock_agentcore.identity.auth import requires_access_token
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool

app = BedrockAgentCoreApp()
memory = MemoryClient(region_name="eu-central-1")


@requires_access_token(provider_name="vault-cognito", scopes=["records.read"], auth_flow="M2M")
async def vault_token(*, access_token: str) -> str:
    return access_token


@tool
def lookup_book(title: str) -> str:
    """Find a book in the library catalogue by its title."""
    return f"{title}: 2 copies available"


agent = Agent(tools=[lookup_book])


@app.entrypoint
def invoke(payload: dict) -> dict:
    result = agent(payload.get("prompt", ""))
    return {"result": str(result)}


if __name__ == "__main__":
    app.run()
