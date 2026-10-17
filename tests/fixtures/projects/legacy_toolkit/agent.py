"""An agent deployed with the deprecated starter toolkit (fixture)."""

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langgraph.graph import StateGraph

app = BedrockAgentCoreApp()
graph = StateGraph(dict)


@app.entrypoint
def invoke(payload):
    return {"ok": True}
