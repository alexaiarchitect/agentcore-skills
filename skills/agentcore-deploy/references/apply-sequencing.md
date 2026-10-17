# Apply sequencing

Terraform derives order from references, so a single `plan`/`apply` of the
right root is normally enough. The stages below are what that order looks
like for AgentCore, and where it goes wrong anyway.

| Stage | Resources | Why it is here |
|---|---|---|
| identity | Cognito clients, KMS keys, workload identities, OAuth2/API key credential providers, token-vault CMK | targets and runtimes reference them |
| roles | the gateway/runtime service roles and policies | AgentCore validates the role when the resource is created |
| core | ECR repository, gateway, runtime, memory, code interpreter, browser | the resources clients will address |
| attachments | gateway targets, memory strategies, runtime endpoints, gateway rules | need the core resource's id |
| telemetry | log groups, log delivery sources/destinations/deliveries, metric alarms | need the resource ARNs |
| guardrails | budgets | independent; last so the first bill is covered |

## What trips a first apply

- **IAM propagation (`DPL003`).** A role created seconds earlier may not yet
  be usable by the service; target creation fails with an access error. Re-run
  the same apply. If it repeats, add `depends_on` from the target to the role
  policy.
- **Implicit sync on target create.** Creating or updating a `DEFAULT`-mode
  MCP server target triggers capability discovery against the upstream: the
  upstream must be reachable and accept the outbound credential **at apply
  time**. An OAuth target can end in `CREATE_PENDING_AUTH`; provider 6.61.0
  treats that as a successful terminal state.
- **Transaction Search before TRACES (`DPL007`).** Run the generated
  `transaction-search.sh` once per account and region first.
- **Creation-only settings (`DPL004`).** Semantic search cannot be added to an
  existing gateway; decide before the first apply.
- **Provider version (`DPL006`).** Arguments such as
  `protocol_configuration.mcp.supported_versions` need a provider that knows
  them; `terraform init -upgrade` within the constraint.

## Terragrunt

When the root has a `terragrunt.hcl` (the first user's
`infrastructure/live/production` does), commands run as `terragrunt plan`
etc. from that directory; Terragrunt generates the backend. Keep `-out` and
`show -json` the same.

## The commands, as emitted

```bash
terraform -chdir=<root> init -input=false
terraform -chdir=<root> validate
terraform -chdir=<root> plan -input=false -out=agentcore.tfplan
terraform -chdir=<root> show -json agentcore.tfplan > agentcore.plan.json
python3 <plugin>/skills/agentcore-ci/scripts/policy_check.py agentcore.plan.json
# only after a human has read the plan and the policy output:
terraform -chdir=<root> apply agentcore.tfplan
```

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html,
https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md (read 2026-10-05); saved-plan and `-destroy -target` behaviour is standard Terraform
(https://developer.hashicorp.com/terraform/cli/commands/plan), not re-read for this plugin.
