# The Runtime container contract

## Per protocol

| Protocol | Port | Paths | Format |
|---|---|---|---|
| HTTP | 8080 | `POST /invocations`, `GET /ping`, `/ws` (WebSocket) | JSON in; JSON or SSE out |
| MCP | 8000 | `POST /mcp` | JSON-RPC over Streamable HTTP |
| A2A | 9000 | `/` | JSON-RPC 2.0; discovery through Agent Cards |
| AG-UI | 8080 | `/invocations` (SSE), `/ws` | event streams |

All: bind **0.0.0.0**, **ARM64** container. Inbound to the runtime is SigV4 or
OAuth 2.0 (a JWT authorizer on the runtime resource); WebSockets accept SigV4
in headers or query parameters.

## HTTP

```
POST /invocations
Content-Type: application/json
{"prompt": "What's the weather today?"}

200 application/json
{"response": "…", "status": "success"}
```

or `text/event-stream` with `data:` lines for streaming.

```
GET /ping
200 {"status": "Healthy"}                      # ready for new work
200 {"status": "HealthyBusy"}                  # busy with async tasks; the session is kept alive
    optional "time_of_last_update": <unix seconds of the last status change>
```

Set `time_of_last_update` only when the status changes — not to "now" on
every ping. `BedrockAgentCoreApp` from the AgentCore Python SDK serves both
endpoints around an `@app.entrypoint` function.

## MCP

Streamable HTTP is required; stateless mode (`stateless_http=True` in
FastMCP) is the default recommendation "for compatibility with AWS's session
management and load balancing". The platform adds an `Mcp-Session-Id` header
for session isolation, and the server must accept it rather than reject an id
it did not issue. No `/ping` is required for MCP.

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("library", host="0.0.0.0", stateless_http=True)
...
mcp.run(transport="streamable-http")   # serves /mcp on 8000
```

A TypeScript server built on the MCP SDK's Streamable HTTP transport without a
session id generator is stateless in the same sense.

## Session headers

| Protocol | Session header |
|---|---|
| MCP | `Mcp-Session-Id` |
| HTTP, A2A, AG-UI | `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` |

## Limits that shape the image

Image ≤ 2 GB; direct code deployment ≤ 250 MB zipped / 750 MB unzipped;
≤ 2 vCPU / 8 GB per session; 1 GB session storage; request timeout 15
minutes; payload 100 MB; streaming 60 minutes; WebSocket frames 64 KB.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html (read 2026-10-05).
