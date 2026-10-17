---
type: llm
---

PASS if the response:

- reports what it found in this project — the MCP route `POST /mcp` and the
  Lambda behind it, the Cognito pool, the region (eu-central-1) — rather than
  describing AgentCore in general;
- states that nothing is on AgentCore yet;
- offers a small number of next steps, each naming a skill and a cost tier
  (free or aws), with one recommended (a gateway in front of the MCP server).

FAIL if it:

- gives advice before inspecting the project;
- writes or generates any file;
- states a region or an AgentCore resource it did not get from a script.
