# Terraform provider coverage

## hashicorp/aws: 21 `aws_bedrockagentcore_*` resources

Read from the provider's `website/docs/r/` on `main` and its CHANGELOG on
2026-10-05 (6.64.0 the latest release noted, 6.65.0 unreleased):

| Area | Resources |
|---|---|
| Runtime | `aws_bedrockagentcore_agent_runtime`, `aws_bedrockagentcore_agent_runtime_endpoint`, `aws_bedrockagentcore_resource_policy` |
| Gateway | `aws_bedrockagentcore_gateway`, `aws_bedrockagentcore_gateway_target`, `aws_bedrockagentcore_gateway_rule` |
| Identity | `aws_bedrockagentcore_workload_identity`, `aws_bedrockagentcore_oauth2_credential_provider`, `aws_bedrockagentcore_api_key_credential_provider`, `aws_bedrockagentcore_token_vault_cmk` |
| Memory | `aws_bedrockagentcore_memory`, `aws_bedrockagentcore_memory_strategy` |
| Built-in tools | `aws_bedrockagentcore_code_interpreter`, `aws_bedrockagentcore_browser`, `aws_bedrockagentcore_browser_profile` |
| Evaluations | `aws_bedrockagentcore_evaluator` (6.51.0), `aws_bedrockagentcore_online_evaluation_config` |
| Policy | `aws_bedrockagentcore_policy`, `aws_bedrockagentcore_policy_engine` |
| Other | `aws_bedrockagentcore_harness`, `aws_bedrockagentcore_registry` (6.52.0) |

Recent arguments worth knowing about: `mcp_server.listing_mode` (6.50.0),
`agent_runtime` `server_protocol = "AGUI"` (6.50.0), `private_endpoint`
(6.55.0), memory strategy `namespace_templates` (6.57.1),
`mcp_server.mcp_tool_schema` (6.59.0), target `http.passthrough`,
`mcp.connector` and `inference` (6.63.0), `self_managed_configuration`
(6.62.0).

`protocol_configuration.mcp.supported_versions` and `search_type` are
documented for `aws_bedrockagentcore_gateway` on `main`, but the release that
introduced `supported_versions` was not found in the CHANGELOG. Before the
first plan on a locked provider (the first user has 6.55.0), confirm it:

```bash
terraform providers schema -json \
  | python3 -c "import json,sys; s=json.load(sys.stdin)['provider_schemas']['registry.terraform.io/hashicorp/aws']['resource_schemas']['aws_bedrockagentcore_gateway']; print(json.dumps(s['block']['block_types']['protocol_configuration'], indent=1))"
```

If it is missing, `terraform init -upgrade` within the constraint, or set the
versions once with `aws bedrock-agentcore-control update-gateway
--protocol-configuration '{"mcp": {"supportedVersions": [...]}}'` and add
`lifecycle { ignore_changes = [protocol_configuration] }` until the provider
catches up.

## Not in hashicorp/aws: use `awscc` or the CLI

CloudFormation types without a hashicorp/aws resource on 2026-10-05:
`CapacityProvider` (Runtime Instances), `ConfigurationBundle`, `Dataset`,
`GatewayRateLimit`, `HarnessEndpoint`, `PaymentConnector`,
`PaymentCredentialProvider`, `PaymentManager`. The `awscc` provider generates
resources from CloudFormation types (`awscc_bedrockagentcore_*`); the exact
names were not confirmed resource by resource, so check the schema first:

```bash
terraform providers schema -json | python3 -c "import json,sys; print('\n'.join(k for k in json.load(sys.stdin)['provider_schemas'].get('registry.terraform.io/hashicorp/awscc',{}).get('resource_schemas',{}) if 'bedrockagentcore' in k))"
```

Observability needs no AgentCore resource: it is
`aws_cloudwatch_log_delivery_source`/`_destination`/`aws_cloudwatch_log_delivery`
plus CloudWatch Transaction Search, which this plugin enables with emitted
`aws xray` commands because no dedicated hashicorp/aws resource for it was
verified.

Sources: https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md,
https://github.com/hashicorp/terraform-provider-aws/tree/main/website/docs/r,
https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_BedrockAgentCore.html,
https://awsfundamentals.com/terraform/bedrockagentcore (all read 2026-10-05).
