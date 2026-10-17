# Semantic search, tool names and gateway quotas

## Semantic tool search

A gateway created with `protocol_configuration.mcp.search_type = "SEMANTIC"`
exposes an extra tool, `x_amz_bedrock_agentcore_search`, that finds tools by
natural-language query — useful when a gateway fronts hundreds of tools and
listing them all would bloat the model's context.

- **Creation-only.** "You can only enable semantic search when creating a
  gateway." Changing it later replaces the gateway and its URL (`GWY008`,
  `DPL004`).
- The creating identity needs `bedrock-agentcore:SynchronizeGatewayTargets`.
- Not combinable with `DYNAMIC` listing on MCP server targets (`ACR054`).
- Regions (checked 2026-10-05): us-east-1, us-east-2, us-west-2, ap-south-1,
  ap-south-2, ap-northeast-1, ap-northeast-2, ap-southeast-1, ap-southeast-2,
  ca-central-1, **eu-central-1**, eu-west-1, eu-west-2, eu-west-3, eu-south-1,
  eu-south-2, eu-north-1, sa-east-1.
- Priced separately: search calls at $0.025 per 1,000 and indexing at $0.02
  per 100 tools per month, on top of $0.005 per 1,000 invocations.
- Quota: search-based tool calls 25 per minute (adjustable).

For a server with a dozen tools (the first user has 14), semantic search adds
cost and a creation-time commitment for no benefit; leave it off.

## Tool names

Clients see `<target name>___<tool name>`. Two limits apply:

| Limit | Source | Check |
|---|---|---|
| 256 characters for the full name (adjustable quota) | AgentCore quotas | `GWY010` error |
| 1–128 characters of `A-Z a-z 0-9 _ - .`, unique, case-sensitive (SHOULD) | MCP 2025-11-25 tools spec | `GWY011` warn |

So a 40-character target name leaves at most 85 characters for tool names if
clients enforce the MCP guidance. Keep target names short and do not put
`___` in them (`GWY013`). A Lambda target must strip the prefix before
dispatch (`GWY014`).

## Gateway quotas (checked 2026-10-05)

| Quota | Value | Adjustable |
|---|---|---|
| gateways per account | 1,000 | yes |
| targets per gateway | 100 | yes |
| tools per target | 1,000 | yes |
| invocation timeout | 15 minutes | yes |
| inline / S3 schema size | 1 MB / 10 MB | yes |
| tools/call and tools/list payload | 6 MB | yes |
| tools/call + tools/list rate, per gateway and per account | 200 TPS | yes |
| concurrent connections, per gateway and per account | 5,000 | yes |
| Create/Update/Delete gateway API | 5 TPS | yes |

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://aws.amazon.com/bedrock/agentcore/pricing/,
https://modelcontextprotocol.io/specification/2025-11-25/server/tools (all read 2026-10-05).
