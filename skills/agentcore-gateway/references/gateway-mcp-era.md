# Which MCP revision AgentCore Gateway speaks

**Finding (checked 2026-10-05):** AgentCore Gateway accepts MCP **2025-03-26,
2025-06-18, 2025-11-25 and 2026-07-28**. Revision **2026-07-28 — the
stateless revision — is supported but opt-in**: a gateway serves it only
when it is listed in `protocolConfiguration.mcp.supportedVersions`
(Terraform: `protocol_configuration { mcp { supported_versions = [...] } }`).
It is not "handshake era only", and it is not 2026-07-28 by default.

## What each era looks like on the wire

| | 2025-03-26 … 2025-11-25 | 2026-07-28 |
|---|---|---|
| handshake | `initialize` → `notifications/initialized` | none |
| session | gateway issues `Mcp-Session-Id`; default timeout 3600 s, configurable 900–28 800 s, absolute from the first `initialize` | none; every request self-contained |
| version | negotiated in `initialize`, then `MCP-Protocol-Version` header | `MCP-Protocol-Version: 2026-07-28` header **and** `params._meta["io.modelcontextprotocol/protocolVersion"]` on every request |
| method | in the body | also in an `Mcp-Method` header |
| client info | in `initialize` | `_meta["io.modelcontextprotocol/clientInfo"]` and `/clientCapabilities` on every request |
| elicitation, sampling | server-initiated | multi round-trip requests (MRTR); responses can carry `resultType: "input_required"` |

A request that carries **no** version header is treated as **2025-03-26**.

## Turning it on

```bash
aws bedrock-agentcore-control update-gateway --gateway-identifier "$GATEWAY_ID" \
  --name "$NAME" --role-arn "$ROLE_ARN" --protocol-type MCP \
  --authorizer-type CUSTOM_JWT --authorizer-configuration file://authorizer.json \
  --protocol-configuration '{"mcp": {"supportedVersions": ["2025-11-25", "2026-07-28"]}}'
```

`UpdateGateway` **replaces** `supportedVersions` with the list sent; it never
appends. Dropping a revision from the list cuts off clients that pin it. In
Terraform the list is the attribute, so a plan shows the change explicitly.

## A dual-version upstream (2025-11-25 + 2026-07-28)

The first user's server is moving to answer both revisions. Behind a gateway
the two sides are independent:

- **Clients ↔ gateway** use whatever the gateway lists. A dual-version
  gateway serves a 2026-07-28 request with the new behaviour and a 2025-11-25
  request with the old one, side by side.
- **Gateway ↔ MCP server target** uses a revision the target supports. When a
  target is on 2026-07-28 and a client is on 2025-*, the gateway translates
  so ordinary tool calls work without the client upgrading. **That
  translation does not cover elicitation or sampling** (`GWY005`). A tool that
  elicits input must be called by a client on the same revision as the
  target, or must not elicit.
- **Sessions do not cross the gateway.** For 2025-era targets the gateway
  initialises its own session with the target on the first call and reuses
  the target's session id; the client's `Mcp-Session-Id` is the gateway's.
  A stateless upstream (no `sessionIdGenerator`) is unaffected.

What this implies for the upstream: it can keep 2025-11-25 alone and still
serve 2026-07-28 clients through the gateway for tools-only use; it needs
2026-07-28 itself only for elicitation/sampling round trips with new clients.
Verify both with `verify.py --protocol both`, which compares the tool lists.

## Response fields new in 2026-07-28

Observed by a third party enabling it (2026-07-30): `resultType`
(`complete` | `input_required`), `ttlMs` and `cacheScope` (e.g. `private`) in
results. Treat these as observed, not contractual, until they appear in the
AgentCore guide.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-sessions.html,
https://aws.amazon.com/blogs/machine-learning/how-agentcore-gateway-supports-the-mcp-2026-07-28-spec/ (2026-07-28),
https://dev.classmethod.jp/en/articles/agentcore-gateway-enable-mcp-2026-07-28/ (2026-07-30),
https://dev.to/mgonzalezo/mcp-new-specs-in-practice-testing-the-stateless-revolution-on-aws-agentcore-gateway-5d49
(2026-08-01) — all read 2026-10-05.
