# Least privilege for AgentCore roles

AgentCore resources act through service roles that trust
`bedrock-agentcore.amazonaws.com`. Each role should allow exactly what its
resource does, on the ARNs it touches.

## The trust policy

```hcl
assume_role_policy = jsonencode({
  Version = "2012-10-17"
  Statement = [{
    Effect    = "Allow"
    Principal = { Service = "bedrock-agentcore.amazonaws.com" }
    Action    = "sts:AssumeRole"
    Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
  }]
})
```

The `aws:SourceAccount` condition prevents a resource in another account from
using the service to assume your role (the confused-deputy pattern). Add
`aws:SourceArn` scoped to your gateway or runtime ARN once it exists.

## Gateway role, by target type

| Target | Outbound auth allowed | The role needs |
|---|---|---|
| Lambda | gateway service role only | `lambda:InvokeFunction` on that function ARN |
| MCP server (OAuth / API key) | none, service role, OAuth (all grants), API key | token-vault reads for the provider, `secretsmanager:GetSecretValue` on the provider's secret ARN |
| MCP server (IAM) | SigV4 with the gateway role | the upstream's action (e.g. `execute-api:Invoke` on the API ARN) |
| OpenAPI | none, service role, OAuth, API key | as for MCP server |
| Smithy | service role, OAuth (client credentials) | the AWS actions the model describes |

A gateway created with semantic search also needs
`bedrock-agentcore:SynchronizeGatewayTargets` for the identity that creates it.

The exact token-vault action names the gateway role needs for OAuth and API
key targets (`GetWorkloadAccessToken`, `GetResourceOauth2Token`,
`GetResourceApiKey` in the generated module) should be confirmed against the
IAM Service Authorization Reference for `bedrock-agentcore` before applying;
the generated module scopes them to `*` with a comment until a narrower
resource form is confirmed, which is why the review reports `ACR022` as a
note on it.

## Runtime role

ECR pull for its repository (`ecr:BatchGetImage`,
`ecr:GetDownloadUrlForLayer`) plus `ecr:GetAuthorizationToken`; logs under
`/aws/bedrock-agentcore/runtimes/*`; `xray:PutTraceSegments` and
`xray:PutTelemetryRecords`; `cloudwatch:PutMetricData` with a
`cloudwatch:namespace = bedrock-agentcore` condition; then whatever the agent
itself calls (a model, a memory, a gateway).

## Lambda behind the gateway

Unchanged from before the gateway, plus X-Ray write
(`AWSXRayDaemonWriteAccess`, or `xray:PutTraceSegments` and
`xray:PutTelemetryRecords`) once active tracing is on. With the ADOT
Application Signals layer, AWS documents
`CloudWatchLambdaApplicationSignalsExecutionRolePolicy`.

## What the review flags

`ACR020` for `*` on `*`, `ACR021` for `service:*` on `*`, `ACR022` for
AgentCore actions on `*` without a condition. Deploy roles used by CI often
carry `service:*` grants; the review reports them, and the user decides.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html,
https://docs.aws.amazon.com/lambda/latest/dg/nodejs-tracing.html,
https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html
(read 2026-10-05). The confused-deputy rationale is IAM's general guidance and was not re-read for this plugin.
