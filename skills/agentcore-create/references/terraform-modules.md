# The generated Terraform modules

All modules require Terraform `>= 1.11` (write-only arguments) and
hashicorp/aws `>= 6.55.0`, and take a `tags` map. Each `main.tf` starts with a
header naming the provider documentation version and date it was checked
against. Nothing is planned or applied by the plugin.

## Runtime (`agentcore-runtime/`)

| Resource | Why |
|---|---|
| `aws_ecr_repository.agent` | immutable tags, scan on push; the image must be `linux/arm64` |
| `aws_iam_role.runtime` + policy | trust `bedrock-agentcore.amazonaws.com` with an `aws:SourceAccount` condition; ECR pull, logs under `/aws/bedrock-agentcore/runtimes/*`, X-Ray, metrics in the `bedrock-agentcore` namespace |
| `aws_bedrockagentcore_agent_runtime.this` | container artifact, `PUBLIC` network mode, `server_protocol`, a `custom_jwt_authorizer`, `environment_variables` (non-secret only), `lifecycle_configuration` (idle timeout 900 s, max lifetime 28 800 s by default) |

Outputs: `agent_runtime_arn`, `agent_runtime_id`, `ecr_repository_url`.

## Gateway (`agentcore-gateway/`)

| Resource | Why |
|---|---|
| `aws_iam_role.gateway` + policy | trust as above; only what the target needs (`lambda:InvokeFunction` on one ARN; or token-vault reads plus `secretsmanager:GetSecretValue` on the provider's secret; `SynchronizeGatewayTargets` when semantic search is on) |
| `aws_bedrockagentcore_gateway.this` | `CUSTOM_JWT` with `discovery_url`, `allowed_clients`, optional `allowed_scopes`; `protocol_type = "MCP"`; `protocol_configuration.mcp.supported_versions` pinned |
| `aws_bedrockagentcore_gateway_target.<name>` | one target: Lambda (gateway role), MCP server (OAuth, API key or IAM) or OpenAPI |

Outputs: `gateway_id`, `gateway_arn`, `gateway_url`, `gateway_role_arn`.
For a gateway in front of something that already exists, use
`/agentcore:agentcore-gateway`, which fills the upstream and Cognito wiring.

## Identity (`agentcore-identity/`)

The default recipe is outbound machine-to-machine through Cognito: a
confidential `aws_cognito_user_pool_client` with `client_credentials`, and an
`aws_bedrockagentcore_oauth2_credential_provider` (`CustomOauth2`) whose
`oauth2_provider_config.custom_oauth2_provider_config` uses `client_id_wo`,
`client_secret_wo` and `client_credentials_wo_version`, with
`oauth_discovery.discovery_url` pointing at the pool. Outputs:
`oauth_provider_arn`, `credential_secret_arn`, `outbound_client_id`. Other
recipes are in `/agentcore:agentcore-identity`.

## Memory (`agentcore-memory/`)

`aws_kms_key.memory` (rotation on), `aws_bedrockagentcore_memory.this` with
`event_expiry_duration` validated to 7–365 days and `encryption_key_arn`, and
one `aws_bedrockagentcore_memory_strategy` per built-in type requested, each
with exactly one actor-scoped namespace template. Outputs: `memory_id`,
`memory_arn`.

## Wiring

The script prints the `module` block; the user adds it to their root module
(for Terragrunt, the stack's `main.tf`). Values that live in other modules —
the Cognito pool, client ids — are passed through those modules' outputs.

Sources: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_gateway,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_gateway_target,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_oauth2_credential_provider,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory_strategy
(the `website/docs/r/` sources on `main`, read 2026-10-05).
