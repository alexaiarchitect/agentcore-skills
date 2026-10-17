# Glossary

**AgentCore** — Amazon Bedrock AgentCore: Runtime, Gateway, Identity, Memory,
built-in tools (Code Interpreter, Browser), Observability, Evaluations, Policy
and newer additions (Harness, Payments, Registry, Optimization), each billed
separately.

**Gateway** — a managed MCP endpoint
(`https://<id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp`) that
turns Lambda functions, OpenAPI and Smithy APIs, and existing MCP servers into
tools, with inbound authorization and per-target outbound credentials.

**Target** — one upstream behind a gateway. Its tools are listed to clients as
`<target name>___<tool name>` (three underscores).

**Inbound auth** — who may call the gateway or runtime: `CUSTOM_JWT` (an OIDC
discovery URL plus allowed clients, audiences, scopes, custom claims),
`AWS_IAM` (SigV4), `AUTHENTICATE_ONLY` (SigV4 identity check, no
authorization decision, no bearer token), or `NONE`.

**Outbound auth** — what the gateway presents to a target: the gateway service
role (IAM/SigV4), OAuth (client credentials, authorization code, token
exchange) or an API key, held by AgentCore Identity.

**Workload identity** — the identity of an agent or gateway as a workload,
independent of where it runs. Gateways and runtimes get one automatically.

**Token vault** — AgentCore Identity's store for OAuth tokens and API keys,
scoped to the agent and user that obtained them.

**Credential provider** — a token-vault entry describing how to obtain a
credential: an OAuth2 provider (e.g. `CustomOauth2` pointed at Cognito's
discovery URL) or an API key provider.

**Runtime** — hosting for agents and MCP servers: one microVM per session,
an ARM64 container (or a code zip), a fixed protocol contract.

**Session** — on Runtime, the unit of isolation (its own microVM); on a
2025-era MCP gateway connection, the `Mcp-Session-Id` from `initialize`.

**Memory** — short-term (raw events per session, 7–365 days) and long-term
(records extracted by strategies, scoped by namespace).

**Transaction Search** — CloudWatch's span store; X-Ray segments are routed
to the `aws/spans` log group, where AgentCore spans also land.

**MCP revision** — a dated version of the Model Context Protocol. Gateway
accepts 2025-03-26, 2025-06-18, 2025-11-25 and (opt-in) 2026-07-28, the
stateless revision with no `initialize` handshake.

**Cost tier** — `free` (files only) or `aws` (commands the user runs against
AWS that may create billable resources).

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-terminology.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using.html (read 2026-10-05).
