# Target types, and what each one changes upstream

A gateway target is one upstream. AgentCore Gateway supports Lambda, OpenAPI,
Smithy and MCP server targets (plus 1-click connectors and, in newer
releases, HTTP passthrough and inference targets). The choice decides whether
the upstream has to change.

## Lambda target

The gateway invokes the function directly. The `event` is a map of the tool's
input properties, and the context carries:

| `context.client_context.custom` field | Meaning |
|---|---|
| `bedrockAgentCoreToolName` | `${target_name}___${tool_name}` — strip the prefix in the handler |
| `bedrockAgentCoreGatewayId`, `bedrockAgentCoreTargetId` | which gateway and target called |
| `bedrockAgentCoreAwsRequestId`, `bedrockAgentCoreMcpMessageId` | request and MCP message ids |
| `bedrockAgentCoreMessageVersion` | the message format version |

Tool schemas are supplied inline (up to 1 MB) or from S3 (up to 10 MB): `name`,
`description`, `inputSchema`, optional `outputSchema`. The function must
return JSON. **Outbound auth: the gateway service role only.**

An existing MCP server on Lambda behind API Gateway does not speak this
contract — its handler expects an API Gateway proxy event carrying a JSON-RPC
body. Making it a Lambda target means writing an adapter handler that maps
`bedrockAgentCoreToolName` to the tool functions (`GWY003`).

## MCP server target

The gateway speaks MCP to an HTTPS endpoint you already serve. Tools are
discovered and indexed when the target is created or updated (`DEFAULT`
listing mode), or listed live (`DYNAMIC`, which cannot be combined with
semantic search or outbound three-legged OAuth); `SynchronizeGatewayTargets`
refreshes the catalogue on demand. The server must have the tools
capability; prompts and resources are synced when advertised. Supported
upstream revisions: 2025-03-26, 2025-06-18, 2025-11-25, 2026-07-28.

**Outbound auth:** none (not recommended), gateway service role (SigV4), OAuth
(client credentials, authorization code, token exchange) or an API key. For a
server that validates Cognito tokens, client credentials from a dedicated
Cognito app client through an OAuth2 credential provider is the direct fit —
with the identity consequence in `GWY002`.

This is the recommended target for the first user's architecture (MCP on
Lambda behind an HTTP API at `/mcp`): nothing upstream changes except that the
API Gateway JWT authorizer and the handler's client allow-list must accept the
gateway's outbound client id (`GWY001`).

## OpenAPI and Smithy targets

Each operation becomes a tool. OpenAPI supports no auth, the service role,
OAuth (all grants) and API keys; Smithy supports the service role and OAuth
client credentials.

## Outbound auth by target

| Target | None | Service role (IAM) | OAuth | API key |
|---|---|---|---|---|
| Lambda | — | yes (only option) | — | — |
| OpenAPI | yes | yes | all grants | yes |
| Smithy | — | yes | client credentials | — |
| MCP server | yes | yes | all grants | yes |

Token passthrough (`JWT_PASSTHROUGH`: the validated inbound token forwarded
unchanged) is "only available for HTTP targets (passthrough and AgentCore
Runtime)" — not for MCP-server targets — and needs a JWT-bearing inbound type
(`CUSTOM_JWT` or `NONE`). `AUTHENTICATE_ONLY` is SigV4 and carries no bearer
token to pass through. For an MCP-server target, carry the user with a REQUEST
interceptor instead (`gateway_plan.py --interceptor forward-jwt`, see
agentcore-identity's identity-propagation.md).

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-building-adding-targets-authorization.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html (read 2026-10-05).
