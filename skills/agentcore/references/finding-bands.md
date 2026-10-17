# Finding bands and exit codes

Every checker emits findings with a stable id, a severity (`error`, `warn`,
`info`), the file and line where it applies, a fix, and a `source` URL.
Ids are stable across releases; tests and skills refer to them.

| Band | Skill | Covers |
|---|---|---|
| `DSC0xx` | agentcore-discover | nothing to read, region unresolved, deprecated starter toolkit, two IaC owners, service unavailable |
| `ACR0xx` | agentcore-review | region availability, inbound JWT, IAM breadth, secrets, observability, targets and outbound auth, Runtime contract, MCP revision pinning, memory, tooling |
| `GWY0xx` | agentcore-gateway | target choice, identity collapse, revisions, semantic search, tool-name length and charset |
| `IDN0xx` | agentcore-identity | Cognito pool and clients, `client_id` vs `aud`, scopes, the outbound principal |
| `RTM0xx` | agentcore-runtime | ARM64, ports, `/ping`, `/invocations`, `/mcp`, statelessness, loopback binding, `.env`, root user, ADOT |
| `MEM0xx` | agentcore-memory | expiry range, strategy types and count, PII and keys |
| `DPL0xx` | agentcore-deploy | backend, quotas, IAM propagation, creation-only settings, provider lock, Transaction Search order |
| `VER0xx` | agentcore-verify | reachability, token refused, empty tool list, tool error, latency over budget, revision mismatch, `/ping` |
| `OBS0xx` | agentcore-observe | traces parsed, p95 vs budget, cold starts, top self time, missing subsegments, tracing config per hop |
| `CST0xx` | agentcore-cost | unpriced services, rate-card change, stale prices, region |
| `CI0xx` | agentcore-ci | deletes of stateful resources, `*` on `*`, open gateway, unpinned revisions, pins, plan role |

## Exit codes (all scripts)

| Code | Meaning |
|---|---|
| 0 | success, no error-level finding |
| 1 | an error-level finding (or, for `review.py --fail-on warn`, a warning) |
| 2 | usage or input error: bad arguments, missing target, unreadable file |
| 3 | inconclusive: the endpoint could not be reached at all (`verify.py`) |

## When the facts were checked

The AgentCore developer guide, pricing page, quotas page and regions page
were read on **2026-10-05**; the Terraform generators follow the hashicorp/aws
documentation on `main` that day (6.64.0 released, 6.65.0 unreleased), and
assume `>= 6.55.0`. The tabular facts live in `lib/agentcore_skills/data/*.json`
with their own `source` and `checked` fields.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://aws.amazon.com/bedrock/agentcore/pricing/ (all read 2026-10-05).
