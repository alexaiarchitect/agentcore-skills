# Review checklist: the `ACR0xx` band

| Id | Severity | Trigger | Fix |
|---|---|---|---|
| `ACR001` | **error** | an AgentCore resource (or gateway semantic search) in a region that does not offer it — e.g. `aws_bedrockagentcore_registry` in eu-central-1 | move it, or drop it |
| `ACR002` | warn | AgentCore resources and no resolvable region | pin `region` or pass `--region` |
| `ACR003` | info | the service/region pair is not in the regions table | confirm on the regions page |
| `ACR010` | **error** | gateway `authorizer_type = "NONE"` | `CUSTOM_JWT` (Cognito) or `AWS_IAM` |
| `ACR011` | **error** | `CUSTOM_JWT` without `custom_jwt_authorizer` | add `discovery_url` and `allowed_clients` |
| `ACR012` | warn | JWT authorizer with no `allowed_clients`, `allowed_audience`, `allowed_scopes` or `custom_claim` | restrict to your clients |
| `ACR013` | **error** | `discovery_url` not ending in `/.well-known/openid-configuration` | the full OIDC configuration URL |
| `ACR014` | info | `AUTHENTICATE_ONLY` | SigV4 identity, no authorization decision: only when the target authorizes the IAM caller itself; no bearer token, so no passthrough |
| `ACR015` | info | an MCP runtime with no JWT authorizer | SigV4 callers only, or add one |
| `ACR020` | **error** | an IAM statement allowing `*` on `*` | scope actions and resources |
| `ACR021` | warn | `service:*` (or `*`) actions on `Resource "*"` | name actions, scope ARNs |
| `ACR022` | info | `bedrock-agentcore:*`-family actions on `*` without a condition | scope to the workload-identity-directory, token-vault and credential-provider ARNs (what `gateway_plan.py` now generates) |
| `ACR030` | **error** | `client_secret`, `api_key` (or `_wo`) as a literal | rotate; pass a sensitive variable |
| `ACR031` | info | `client_secret`/`api_key` from a variable on an AgentCore resource (stored in state) | use the `_wo` argument |
| `ACR032` | warn | a variable named like a credential without `sensitive = true` | mark it sensitive |
| `ACR033` | **error** | a Dockerfile copies `.env` | remove; rotate what it held |
| `ACR040` | warn | AgentCore resources with no `aws_cloudwatch_log_delivery_source` | add APPLICATION_LOGS and TRACES delivery |
| `ACR041` | warn | log delivery but no `TRACES` source for a gateway/runtime | add TRACES → XRAY |
| `ACR042` | info | no evidence of Transaction Search | `aws xray update-trace-segment-destination --destination CloudWatchLogs` |
| `ACR043` | warn | a Lambda behind `/mcp` or a gateway target with `tracing_config` not `Active` | `mode = "Active"` + X-Ray write permission |
| `ACR044` | info | such a Node.js Lambda with no ADOT layer and no tracer in code (an in-repo emitter reading `_X_AMZN_TRACE_ID` / `AWS_XRAY_DAEMON_ADDRESS` counts once tracing is `Active`) | AWSOpenTelemetryDistroJs layer, or Powertools Tracer |
| `ACR045` | info | an API Gateway HTTP API (cannot be X-Ray traced) | read its share from the access log |
| `ACR050` | warn | MCP-server or OpenAPI target without `credential_provider_configuration` | OAuth, API key or IAM |
| `ACR051` | **error** | Lambda target with anything but `gateway_iam_role` | Lambda targets support only the gateway service role |
| `ACR052` | **error** | MCP server endpoint over `http://` | HTTPS |
| `ACR053` | info | target configuration could not be read | check by hand |
| `ACR054` | **error** | `listing_mode = "DYNAMIC"` on a gateway with semantic search | DEFAULT listing, or no semantic search |
| `ACR060` | **error** | a Dockerfile in a Runtime project not built for `linux/arm64` | `FROM --platform=linux/arm64` |
| `ACR061` | warn | HTTP runtime with no `/ping` handler | `{"status": "Healthy"}` |
| `ACR062` | warn | Python MCP server without `stateless_http=True` | accept the platform `Mcp-Session-Id` |
| `ACR063` | warn | `EXPOSE` does not include the protocol's port | 8080 HTTP/AG-UI, 8000 MCP, 9000 A2A |
| `ACR070` | info | gateway without pinned `supported_versions` | pin the revisions you test |
| `ACR071` | **error** | `supported_versions` lists a revision Gateway does not accept | 2025-03-26, 2025-06-18, 2025-11-25, 2026-07-28 |
| `ACR080` | **error** | `event_expiry_duration` outside 7–365 | choose 7–365 days |
| `ACR081` | info | memory without `encryption_key_arn` | customer-managed key for personal data |
| `ACR082` | **error** | more than 6 strategies on one memory | merge or drop |
| `ACR090` | warn | hashicorp/aws locked below 6.55.0 with AgentCore resources | `init -upgrade` |
| `ACR095` | warn | `.bedrock_agentcore.yaml` (starter toolkit) | Terraform here, or the AgentCore CLI |

Severity is the default; the review never escalates on its own. Use
`--fail-on warn` in CI if warnings should block.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html,
https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html (read 2026-10-05).
