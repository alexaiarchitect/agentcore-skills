# What discovery detects

Discovery combines two readers over the same tree: an HCL reader for
Terraform and a code reader for everything else. Both skip `.terraform`,
`.terragrunt-cache`, `node_modules`, `.git`, `cdk.out`, virtualenvs and build
output.

## AgentCore resources and their owners ("doors")

| Door | Evidence | Meaning |
|---|---|---|
| `terraform` | `resource "aws_bedrockagentcore_*"` or `"awscc_bedrockagentcore_*"` | Terraform owns these; this plugin's generators fit here |
| `cdk` | `aws-cdk-lib/aws-bedrockagentcore`, `Cfn(Runtime\|Gateway\|...)`, `@aws/agentcore-cdk` | a CDK app owns them |
| `agentcore-cli` | `agentcore.json` | the AgentCore CLI (`@aws/agentcore`) owns them through its own CDK app |
| `starter-toolkit` | `.bedrock_agentcore.yaml` | the Python starter toolkit; its CLI is no longer supported (`DSC003`) |
| `sdk-calls` | `boto3.client("bedrock-agentcore"\|"bedrock-agentcore-control")`, `@aws-sdk/client-bedrock-agentcore` | resources created or called from code |
| `agentcore-python-sdk` | `from bedrock_agentcore...` | the runtime app wrapper, memory client or identity decorators |

More than one owning door (`terraform`, `cdk`, `agentcore-cli`,
`starter-toolkit`) is `DSC004`: decide on one owner per resource before
generating anything.

## The application

- **MCP endpoint.** `aws_apigatewayv2_route` keys ending in `/mcp` (including
  `for_each` sets), followed through `target = "integrations/${...}"` to the
  integration, and through `integration_uri = aws_lambda_function.X.invoke_arn`
  to the function. That function is the one whose tracing matters.
- **MCP server code.** TypeScript imports of `@modelcontextprotocol/sdk` (or
  the v2 `@modelcontextprotocol/server`/`/node` packages) with `server` in the
  path; Python `mcp.server.fastmcp`/`fastmcp`. `stateless_http=True` is
  recorded for the Runtime contract.
- **Agent entry points.** `@app.entrypoint` (BedrockAgentCoreApp), which also
  implies `/invocations` and `/ping`.
- **Containers.** Every Dockerfile: `FROM --platform`, `EXPOSE`, `USER`,
  `CMD`, whether `.env` is copied, whether `opentelemetry-instrument` is used.

## Auth

`aws_cognito_user_pool`, `aws_cognito_user_pool_client` (with its OAuth
flows), `aws_cognito_resource_server`, API Gateway JWT authorizers, and the
authorizer type of any AgentCore gateway. Discovery does not judge them; the
identity and review skills do.

## Region

In order: a literal `region` on an un-aliased `provider "aws"`; a
`var.<name>` there resolved through the variable's default; then mentions in
`terragrunt.hcl`, `backend.tf`, `terraform.tfvars`, `aws-targets.json` and
`.env.example`. The availability row is computed from the regions table
(checked 2026-10-05), which has explicit limited-availability lists for
Runtime Instances, Payments, Registry, the Web Search tool and Gateway
semantic search.

## Terraform

`required_version`, the hashicorp/aws constraint (merged across files), the
locked version from `.terraform.lock.hcl`, whether `awscc` is in use, and
Terragrunt stacks.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/develop-agents.html,
https://pypi.org/project/bedrock-agentcore-starter-toolkit/,
https://github.com/aws/agentcore-cli (read 2026-10-05).
