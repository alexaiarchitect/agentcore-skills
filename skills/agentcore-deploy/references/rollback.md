# Rollback

Decide the rollback before the apply. The right one depends on what changed.

| Change | Rollback | Notes |
|---|---|---|
| a new gateway target or credential | revert the commit, plan, apply | the gateway and its URL stay; clients see the old tool list |
| gateway inbound settings (authorizer, allowed clients) | set the previous values, plan, apply | in-place update |
| `supported_versions` | apply the previous list | `UpdateGateway` replaces the list exactly; removing a revision cuts off clients pinned to it |
| a runtime image | point `image_tag` at the previous immutable tag, apply | sessions already running keep their microVM until they stop |
| the whole new AgentCore layer | `plan -destroy -target=<target addresses> -out=rollback.tfplan`, review, apply; then the gateway the same way | targets first, then the gateway; clients pointed at the gateway URL break |
| semantic search turned on by mistake | a new gateway without it, clients moved, then the old one destroyed | creation-only; there is no in-place undo |

## Never part of a rollback

- **Cognito user pools** — every user's identity and the token issuer.
- **AgentCore Memory** — conversations and extracted records.
- **Credential providers and workload identities** — secrets in the token
  vault, and identities other resources reference.
- **Application data stores** (DynamoDB tables).

The CI policy (`CI001`) refuses a plan that deletes or replaces any of these
unless the exact address is passed to `--allow-replace` after review.

## When the apply half-failed

Terraform records what it created. Fix the cause (usually IAM propagation or
an upstream that refused the outbound credential during the target's
implicit sync) and re-run the same plan/apply; do not hand-delete resources in
the console, which leaves state pointing at nothing.

## After rolling back

Run `/agentcore:agentcore-verify` against what remains: the upstream directly
if the gateway is gone, or the gateway with `--protocol both` if only a
target or setting was reverted.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html,
https://aws.amazon.com/blogs/machine-learning/how-agentcore-gateway-supports-the-mcp-2026-07-28-spec/,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html (read 2026-10-05); saved-plan and `-destroy -target` behaviour is standard Terraform
(https://developer.hashicorp.com/terraform/cli/commands/plan), not re-read for this plugin.
