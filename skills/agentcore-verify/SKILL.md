---
name: agentcore-verify
description: >-
  Verify a deployed Amazon Bedrock AgentCore setup from the outside, with a
  script rather than a hunch: call the Gateway's MCP endpoint with a real
  bearer token (read from an environment variable, never printed), in the
  2025 handshake era (`initialize` → `Mcp-Session-Id` → `tools/list`) and/or
  the stateless 2026-07-28 revision (`MCP-Protocol-Version` and `Mcp-Method`
  headers plus `_meta`), check that the expected `<target>___<tool>` names
  are listed, make one tool call, repeat it for p50/p95 against a latency
  budget (default 500 ms), compare the two revisions, and check a Runtime
  container's `/ping`. Emits the read-only `aws` commands for what only AWS
  can answer (gateway and target status, credential providers, workload
  identities, X-Ray traces over budget, gateway Latency/TargetExecutionTime
  metrics, an InvokeAgentRuntime smoke call). Findings are the `VER0xx`
  band; `--dry-run` shows the requests and sends nothing. Use when asked "is
  the gateway working", "smoke test the deploy", "does tools/list work",
  "check both MCP versions", "what is the p95 through the gateway", "is the
  runtime healthy". Don't use before anything is deployed (use
  `/agentcore:agentcore-review`), for finding which hop is slow (use
  `/agentcore:agentcore-observe` on exported traces), or for load testing.
argument-hint: "--gateway-url URL [--protocol 2025-11-25|2026-07-28|both]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Verify what is deployed

A deploy is finished when a real client, with a real token, gets the tools
it expects and a call returns inside the budget — in every MCP revision the
gateway claims to serve. This skill checks exactly that, and prints the AWS
commands for the facts only AWS holds.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Show the plan first.** The token goes in an environment variable the
   user sets themselves (for Cognito machine clients, from the token endpoint
   with client credentials):

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/verify.py --gateway-url <gateway_url> --token-env GATEWAY_TOKEN --protocol both --call <tool> --dry-run
   ```

2. **Confirm** with `AskUserQuestion` (tier `aws`: real calls against the
   user's gateway, billed per 1,000 invocations, reaching their upstream),
   then run without `--dry-run`, adding `--samples 20 --budget-ms 500` for
   latency and `--expect-tool <name>` for each tool that must be listed.

3. **AWS-side checks.** Print them; the user runs them and pastes results:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/aws_checks.py <project> --gateway-id <id> --service-name <lambda function name>
   ```

4. **Report**: per revision, initialize (2025) or not (2026-07-28), the tool
   list, the call result, p50/p95 against the budget; then `VER` findings.
   Latency measured from a laptop includes its network round trip; say so,
   and compare with X-Ray's server-side numbers.

5. **Next:** over budget → `/agentcore:agentcore-observe` with traces
   exported for these calls; a refused token → `/agentcore:agentcore-identity`.

## The `VER0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `VER001` | **error** | the endpoint could not be reached (exit 3 if nothing was) |
| `VER002` | **error** | 401/403: the token was refused |
| `VER003` | **error** | `tools/list` returned nothing |
| `VER004` | **error** | the tool call returned `isError` |
| `VER005` | warn | p95 over the budget |
| `VER006` | **error** | a JSON-RPC or HTTP error during the probe |
| `VER007` | warn | the gateway negotiated a different revision than requested |
| `VER008` | **error** | an expected tool is not listed |
| `VER009` | **error** | `/ping` is not 200 with `Healthy`/`HealthyBusy` |
| `VER010` | warn | no token in the named variable |
| `VER011` | warn | the two revisions list different tools |

## Decision rules

- **A 401 with no token proves only that the authorizer is on.** Always
  verify with a token from a client in `allowed_clients`.
- **Both revisions, if both are pinned.** A gateway listing 2026-07-28 that
  was only tested with 2025-11-25 is untested.
- **p95 needs samples.** Fewer than 20 calls make p95 the maximum; the
  report says so.
- **Two users, two owners.** When identity propagation was designed in
  (`agentcore-identity`), verify with two users' tokens and check the
  upstream recorded two different owners.

## References

| Question | File |
|---|---|
| What each check proves and does not | [verify-checks.md](references/verify-checks.md) |
| The two MCP handshakes on the wire | [mcp-handshakes.md](references/mcp-handshakes.md) |
| Reading p50/p95 against a 500 ms budget | [latency-budget.md](references/latency-budget.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/verify.py --gateway-url URL [--protocol P\|both] [--call T] [--samples N] [--budget-ms B] [--ping-url U] [--dry-run] [--json]` | live MCP and `/ping` checks | 0 pass, 1 a check failed, 2 bad arguments, 3 unreachable |
| `scripts/aws_checks.py <project> [--gateway-id ID] [--runtime-arn ARN] [--json]` | read-only `aws` commands to run | 0, 2 bad arguments |

## Completion checklist

- [ ] The dry run was shown and the user confirmed before any real call.
- [ ] The token came from an environment variable and appears nowhere in the output.
- [ ] Every pinned MCP revision was probed, and their tool lists compared.
- [ ] p50/p95 were reported with the sample count and the budget, and the network caveat stated.
- [ ] The AWS-side commands were handed over, not run.
