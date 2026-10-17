# Build, deploy and invoke

## Build and push (the user runs these)

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
docker buildx build --platform linux/arm64 -t "$REPO_URL:$TAG" --push .
```

Use an immutable tag (the generated ECR repository sets
`image_tag_mutability = "IMMUTABLE"`), and pass it to the module's
`image_tag` variable so a plan shows exactly which image is deployed.

## Deploy

The Terraform resource is `aws_bedrockagentcore_agent_runtime` with
`agent_runtime_artifact.container_configuration.container_uri`,
`network_configuration.network_mode`, `protocol_configuration.server_protocol`
(`HTTP`, `MCP`, `A2A`, `AGUI`), an optional `authorizer_configuration`,
`environment_variables` and `lifecycle_configuration`. It exports
`agent_runtime_arn`, `agent_runtime_id`, `agent_runtime_version` and the
runtime's workload identity. Endpoints (aliases) are
`aws_bedrockagentcore_agent_runtime_endpoint`; up to 10 per agent.

`/agentcore:agentcore-deploy` prints the plan/apply sequence; nothing here
applies it.

## Invoke

Data plane, SigV4:

```bash
aws bedrock-agentcore invoke-agent-runtime --region "$AWS_REGION" \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$(python3 -c 'import uuid;print(uuid.uuid4().hex + "-session")')" \
  --payload '{"prompt": "ping"}' --cli-binary-format raw-in-base64-out /dev/stdout
```

From Python, `InvokeAgentRuntime(agentRuntimeArn=…, runtimeSessionId=…,
payload=…)`. A runtime with a JWT authorizer is called with a bearer token
instead of SigV4. For an MCP runtime, an MCP client connects to the runtime's
MCP endpoint and sends `Mcp-Session-Id`.

## Quotas to check before a launch (checked 2026-10-05)

| Quota | Value |
|---|---|
| active session workloads | 5,000 (US East/West), 2,500 elsewhere (adjustable) |
| new sessions | 25 TPS (adjustable) |
| data-plane requests | 1,000 TPS (adjustable) |
| agents per account | 1,000; versions per agent 1,000 |
| control-plane mutations | 50 TPS |

## Pricing (microVMs v2, list)

$0.1276 per vCPU-hour and $0.0169 per GB-hour, per second, 1-second minimum;
CPU scales to zero during I/O wait; memory reclaimed after 120 s idle. A
committed baseline ($0.0997 / $0.0132) launches October 2026. Runtime
Instances are EC2 price plus a management fee.

Sources: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://aws.amazon.com/bedrock/agentcore/pricing/ (read 2026-10-05). The `invoke-agent-runtime`
CLI shape follows the `InvokeAgentRuntime` API name; confirm with `aws bedrock-agentcore invoke-agent-runtime help`.
