---
name: agentcore-gateway
description: >-
  Put an Amazon Bedrock AgentCore Gateway in front of something that already
  exists — a Lambda function, an HTTP/OpenAPI service, or an MCP server (for
  example a TypeScript MCP server on Lambda behind API Gateway at `/mcp`).
  Makes the target-type decision explicit (an MCP server target needs no
  upstream change; a Lambda target changes the handler contract to tool
  arguments plus `bedrockAgentCoreToolName`), configures inbound `CUSTOM_JWT`
  from the project's Cognito pool through its module outputs (discovery URL,
  `allowed_clients` on the `client_id` claim, scopes), outbound credentials
  through AgentCore Identity, pinned MCP revisions (2025-11-25 and the opt-in
  stateless 2026-07-28), optional semantic tool search (creation-only), and
  tool-name limits (`<target>___<tool>`, 256 characters). Writes Terraform
  after a dry run; findings are the `GWY0xx` band. Use when asked to "put a
  gateway in front of my Lambda", "front my MCP server with AgentCore",
  "AgentCore Gateway with Cognito", "which MCP version does the gateway
  speak", "turn on 2026-07-28", "semantic tool search", "are my tool names
  too long". Don't use for a brand-new gateway with nothing behind it yet
  (use `/agentcore:agentcore-create`), for identity recipes beyond the
  gateway's outbound credential (use `/agentcore:agentcore-identity`), or to
  migrate the MCP server's own protocol version.
argument-hint: "[project-dir] [--upstream auto|mcp|lambda|openapi]"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# A gateway in front of what you have

A gateway changes three contracts at once: who may call (inbound JWT), what
the upstream sees (an outbound credential that is the gateway's, not the
user's), and which MCP revision clients speak. Each has a choice with a
consequence, so this skill makes the choices visible before writing anything.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover** the upstream, the Cognito pool and the region:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-discover/scripts/discover.py <project> --focus app,auth,region
   ```

2. **Plan** the gateway, read-only:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gateway_plan.py <project> --dry-run
   ```

   `--upstream auto` picks `mcp` when an `/mcp` route or MCP server exists.
   `--endpoint`, `--lambda-ref`, `--outbound oauth|api_key|iam|none`,
   `--versions 2025-11-25,2026-07-28`, `--semantic`, `--tools tools.json`
   (Lambda), `--with-identity` (also write the Cognito M2M outbound module;
   `--client-ref aws_cognito_user_pool_client.x` reuses an existing client),
   `--interceptor forward-jwt|signed-claim|<lambda arn>` (a REQUEST interceptor
   that carries the user's identity in `params._meta[--meta-key]`, with its
   Lambda, role and wiring), `--out-dir DIR` (the modules directory: every
   module goes to `DIR/<module>`).

3. **Check tool names** as the gateway will expose them:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/tool_names.py [probe.json] --from-code <server src> \
       --target-name <target> --target-type mcp
   ```

   A probe report or `tools/list` JSON counts exactly what the server lists.

4. **Report and decide.** Read out the target type, the inbound wiring, the
   outbound credential and the `GWY` findings. `GWY002` (the outbound token
   is the gateway's, not the user's) is a design decision, not a typo: walk
   through [identity-propagation.md](../agentcore-identity/references/identity-propagation.md)
   before going further; `--interceptor forward-jwt` generates its option C. Options: MCP-server target (recommended when the
   upstream speaks MCP), Lambda target with an adapter, OpenAPI target. All
   free to generate.

5. **Confirm** with `AskUserQuestion`, write (same command without
   `--dry-run`), give the user the printed `module` wiring block, then run
   `${CLAUDE_SKILL_DIR}/../agentcore-review/scripts/review.py` and show it.

## The `GWY0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `GWY001` | info | the upstream's own JWT authorizer must also accept the gateway's outbound client |
| `GWY002` | warn | client-credentials outbound: the upstream sees one machine principal for every user |
| `GWY003` | **error** | a Lambda target on a function that serves MCP over API Gateway |
| `GWY004` | **error** | semantic search in a region that does not offer it |
| `GWY005` | info | 2026-07-28 clients through a 2025-era upstream: no elicitation or sampling translation |
| `GWY006` | warn | no MCP endpoint URL resolved |
| `GWY007` | **error** | an MCP revision Gateway does not accept |
| `GWY008` | info | semantic search is creation-only |
| `GWY009` | warn | no Cognito pool found |
| `GWY010` | **error** | `<target>___<tool>` longer than the 256-character quota |
| `GWY011` | warn | outside the MCP tool-name guidance (1–128 of `A-Za-z0-9_.-`) |
| `GWY012` | **error** | duplicate tool name |
| `GWY013` | warn | target name contains `___` |
| `GWY014` | info | a Lambda target must strip the prefix itself (only for `--target-type lambda`, or when no type is given) |
| `GWY015` | warn | `--with-identity` could not apply (outbound is not oauth, or a Lambda upstream) |
| `GWY016` | warn | an interceptor asked for on a Lambda-target gateway |
| `GWY017` | info | the interceptor writes `params._meta[<key>]`: what the upstream must verify and strip |

## Decision rules

- **If it speaks MCP, use an MCP server target.** The Lambda target contract
  (`event` = tool arguments) is not an API Gateway proxy event; pointing it
  at an MCP-over-HTTP handler fails on the first call (`GWY003`).
- **`allowed_clients`, not `allowed_audience`, for Cognito.** Access tokens
  carry `client_id`; `aud` appears only with a resource binding, and never in
  client-credentials tokens.
- **Pin revisions; 2026-07-28 is opt-in.** `UpdateGateway` replaces the list;
  it never appends. Requests with no version header are treated as
  2025-03-26. See [gateway-mcp-era.md](references/gateway-mcp-era.md).
- **Semantic search now or never.** Enabling it later means a new gateway URL.

## References

| Question | File |
|---|---|
| Lambda vs MCP server vs OpenAPI vs Smithy targets; outbound auth per type | [target-types.md](references/target-types.md) |
| Inbound JWT from Cognito: discovery URL, client_id vs aud, scopes | [inbound-jwt-cognito.md](references/inbound-jwt-cognito.md) |
| Which MCP revision Gateway speaks, and the dual-version upstream | [gateway-mcp-era.md](references/gateway-mcp-era.md) |
| Semantic search, tool names, quotas | [semantic-search-and-limits.md](references/semantic-search-and-limits.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/gateway_plan.py <project> [options] [--dry-run] [--force] [--json]` | target decision, `GWY` findings, the Terraform module and its wiring | 0 planned/written, 1 an error finding, 2 bad arguments |
| `scripts/tool_names.py [tools.json] [--from-code DIR] --target-name T [--target-type mcp\|lambda\|openapi] [--json]` | names as the gateway lists them, against limits | 0 no errors, 1 errors, 2 no input |

## Completion checklist

- [ ] The target type was chosen with the user, and `GWY003` (if any) was explained.
- [ ] Inbound wiring uses the Cognito module's outputs and `allowed_clients`.
- [ ] The identity consequence of the outbound credential (`GWY002`) was discussed before writing.
- [ ] MCP revisions were pinned explicitly, and the 2026-07-28 opt-in was stated.
- [ ] Tool names were checked with `tool_names.py`.
- [ ] The write plan was confirmed, the wiring block given, and `review.py` re-run.
