# The two MCP handshakes, as `verify.py` sends them

## 2025-03-26 … 2025-11-25 (sessionful)

```http
POST /mcp
Authorization: Bearer <token>
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":"verify-1","method":"initialize",
 "params":{"protocolVersion":"2025-11-25","capabilities":{},
           "clientInfo":{"name":"agentcore-skills-verify","version":"0.1.0"}}}
```

The response carries `Mcp-Session-Id` (a header) and the negotiated
`protocolVersion` (in the result). Then:

```http
POST /mcp
MCP-Protocol-Version: 2025-11-25
Mcp-Session-Id: <id>
{"jsonrpc":"2.0","method":"notifications/initialized"}

POST /mcp
MCP-Protocol-Version: 2025-11-25
Mcp-Session-Id: <id>
{"jsonrpc":"2.0","id":"verify-2","method":"tools/list"}
```

The gateway session lasts 3,600 s by default (900–28,800 s configurable),
counted from the first `initialize`.

## 2026-07-28 (stateless)

No `initialize`, no session. Every request is self-contained:

```http
POST /mcp
Authorization: Bearer <token>
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/list
Content-Type: application/json

{"jsonrpc":"2.0","id":"verify-1","method":"tools/list",
 "params":{"_meta":{
   "io.modelcontextprotocol/protocolVersion":"2026-07-28",
   "io.modelcontextprotocol/clientInfo":{"name":"agentcore-skills-verify","version":"0.1.0"},
   "io.modelcontextprotocol/clientCapabilities":{}}}}
```

The gateway serves this only if 2026-07-28 is in `supportedVersions`.

## Without a version header

A request with no `MCP-Protocol-Version` header is treated as 2025-03-26.

## Response bodies

Either `application/json` or `text/event-stream` with `data:` lines carrying
JSON-RPC messages; the client reads both and matches the response by `id`.
Tool calls return `result.content` and `result.isError`; protocol problems
return a JSON-RPC `error` (`VER006`).

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-sessions.html,
https://aws.amazon.com/blogs/machine-learning/how-agentcore-gateway-supports-the-mcp-2026-07-28-spec/,
https://dev.classmethod.jp/en/articles/agentcore-gateway-enable-mcp-2026-07-28/,
https://modelcontextprotocol.io/specification/2025-11-25/server/tools (read 2026-10-05).
