# Policy gates (`CI0xx`)

`policy_check.py` reads `terraform show -json <planfile>` — the
`resource_changes` list with each change's `actions` and planned `after`
values — and nothing else. It needs no credentials and no network.

## Refused (exit 1)

**`CI001` delete or replace of a stateful resource.** A change whose actions
include `delete` (alone, or with `create` for a replacement) on:

| Type | What would be lost |
|---|---|
| `aws_bedrockagentcore_memory` | conversations and long-term records |
| `aws_bedrockagentcore_gateway` | the gateway URL every client is configured with |
| `aws_bedrockagentcore_oauth2_credential_provider` | the client secret in the token vault |
| `aws_bedrockagentcore_api_key_credential_provider` | the API key in the token vault |
| `aws_bedrockagentcore_workload_identity` | an identity other resources reference |
| `aws_cognito_user_pool` | every user's identity, and the token issuer |
| `aws_dynamodb_table` | application data |

Replacements are often accidental: a renamed resource, a changed
creation-only argument (semantic search on a gateway, a memory's name). The
fix is usually to revert that argument or add a `moved` block. When a
replacement is genuinely intended, a human reviews the plan and the job is
re-run with `--allow-replace <exact address>`; the allowance covers that
address only.

**`CI002` `*` on `*`.** A planned IAM policy statement allowing every action
on every resource.

**`CI003` an open gateway.** A gateway created or updated with
`authorizer_type = "NONE"`.

## Reported

**`CI004`** a gateway without `supported_versions` (warn): which MCP
revisions it serves is then a default, not a decision. **`CI005`** no changes.
**`CI006`** the AgentCore resources being created — the plan's billing
surface, for the reviewer.

## Running it locally

```bash
terraform -chdir=infrastructure/live/production plan -out=agentcore.tfplan
terraform -chdir=infrastructure/live/production show -json agentcore.tfplan > agentcore.plan.json
python3 <plugin>/skills/agentcore-ci/scripts/policy_check.py agentcore.plan.json
```

## Extending

Rules live in `lib/agentcore_skills/plan_policy.py`, which must stay free of
relative imports because it is vendored into CI. Add a type to `STATEFUL` to
protect it; add a rule with a new `CI0xx` id and a test with a plan fixture.

Sources: https://developer.hashicorp.com/terraform/internals/json-format (the plan JSON format; standard
Terraform behaviour, not re-read for this plugin); https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html
and https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html (read 2026-10-05).
