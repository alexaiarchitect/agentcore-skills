# Credential providers

## OAuth2 providers

`credential_provider_vendor` values in the hashicorp/aws provider:
`CustomOauth2`, `GithubOauth2`, `GoogleOauth2`, `Microsoft`,
`SalesforceOauth2`, `SlackOauth2`. The `oauth2_provider_config` block holds
exactly one of `custom_oauth2_provider_config`, `github_oauth2_provider_config`,
`google_oauth2_provider_config`, `microsoft_oauth2_provider_config`,
`salesforce_oauth2_provider_config`, `slack_oauth2_provider_config`.

Each accepts either `client_id`/`client_secret` (stored in state) or the
write-only `client_id_wo`/`client_secret_wo` with
`client_credentials_wo_version`. A custom provider adds `oauth_discovery`,
with either `discovery_url` or `authorization_server_metadata` (`issuer`,
`authorization_endpoint`, `token_endpoint`, `response_types`) — not both.

Exported: `credential_provider_arn`, and `client_secret_arn` (the Secrets
Manager secret AgentCore keeps the client secret in).

## API key providers

```hcl
resource "aws_bedrockagentcore_api_key_credential_provider" "upstream" {
  name               = "upstream-api-key"
  api_key_wo         = var.api_key   # sensitive, ephemeral variable
  api_key_wo_version = 1
}
```

Exported: `credential_provider_arn`, `api_key_secret_arn`. A target uses it as
`credential_provider_configuration { api_key { provider_arn, credential_location
= "HEADER" | "QUERY_PARAMETER", credential_parameter_name, credential_prefix } }`.

## Grant types on gateway targets

| Grant | Flow | When |
|---|---|---|
| `CLIENT_CREDENTIALS` | two-legged | machine-to-machine; one principal for all users |
| `AUTHORIZATION_CODE` | three-legged | the user consents once; tokens per user in the vault; authorization URL and session URI valid 10 minutes |
| `TOKEN_EXCHANGE` | on-behalf-of | the gateway exchanges the inbound user token for a scoped downstream token carrying user and agent identity |

The Terraform `oauth` block documents `provider_arn`, `scopes`,
`custom_parameters`, `default_return_url` and `grant_type`; the casing of
`grant_type` values is inconsistent in the documentation examples, so the
generated module notes it should be confirmed against the provider schema.

## Write-only arguments and Terraform versions

Write-only arguments need Terraform 1.11 or later; an `ephemeral` variable
(1.10+) keeps the input out of the plan as well. On older Terraform, use a
`sensitive` variable and accept that the value is in state (`ACR031`).

## Quotas

50 OAuth2 and 50 API key providers per account and region (adjustable).

Sources: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_oauth2_credential_provider,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_api_key_credential_provider,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_gateway_target,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html (read 2026-10-05).
