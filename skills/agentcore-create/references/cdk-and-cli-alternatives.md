# CDK and the AgentCore CLI

Terraform is recommended, but two other paths exist and a team already on one
of them should stay on it. Mixing owners for the same resource is `DSC004`.

## CDK (`--iac cdk`)

CloudFormation has `AWS::BedrockAgentCore::*` resource types (Runtime,
RuntimeEndpoint, Gateway, GatewayTarget, Memory, OAuth2CredentialProvider,
ApiKeyCredentialProvider, WorkloadIdentity, and more), so aws-cdk-lib exposes
L1 constructs for them under `aws-cdk-lib/aws-bedrockagentcore`. The
generated stack uses `CfnGateway`, `CfnRuntime`, `CfnMemory` or
`CfnOAuth2CredentialProvider` with CloudFormation property names
(`authorizerConfiguration.customJwtAuthorizer.discoveryUrl`, …) and a service
role trusted by `bedrock-agentcore.amazonaws.com` with an
`aws:SourceAccount` condition.

The plugin did not run `cdk synth` against these; the stack header says to
run it before deploying, which validates every property name against the
installed aws-cdk-lib. Review and CI policy in this plugin read Terraform
only; for CDK, review `cdk diff` instead.

## The AgentCore CLI (`--iac cli`)

`npm install -g @aws/agentcore` (Node.js 20+). It keeps every resource in
`agentcore.json`, deployment targets in `aws-targets.json`, local API keys in
`.env.local` (gitignored), and deploys through CDK constructs from
`@aws/agentcore-cdk`. Commands printed by the scaffold:

| Component | Commands |
|---|---|
| runtime | `agentcore create`, `agentcore dev`, `agentcore deploy`, `agentcore invoke` |
| gateway | `agentcore add gateway --name … --authorizer-type CUSTOM_JWT --discovery-url … --allowed-audience …`, then `agentcore deploy` |
| identity | `agentcore add credential --name … --type oauth --discovery-url … --client-id … --client-secret …` |
| memory | `agentcore add memory`, then `agentcore deploy` |

Choose it for a greenfield agent where the team wants the CLI's local dev
loop, built-in evaluations and the official `aws-agents` plugin's guidance.

## The starter toolkit

`bedrock-agentcore-starter-toolkit` (PyPI, latest 0.3.13 on 2026-09-15)
states that its CLI is no longer supported and recommends the AgentCore CLI.
A project with `.bedrock_agentcore.yaml` gets `DSC003`/`ACR095`; migrate it
to Terraform or the AgentCore CLI rather than extending it.

Sources: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_BedrockAgentCore.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/develop-agents.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create-cli.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started-cognito.html,
https://github.com/aws/agentcore-cli, https://pypi.org/project/bedrock-agentcore-starter-toolkit/ (read 2026-10-05).
