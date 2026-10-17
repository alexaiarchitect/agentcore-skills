# Neighbours: the official `aws-agents` plugin and the AgentCore CLI

## `aws-agents` (claude-plugins-official)

Anthropic's official marketplace lists `aws-agents`, sourced from
`https://github.com/aws/agent-toolkit-for-aws.git` at `plugins/aws-agents`,
described as: "Build, deploy, and operate AI agents on AWS. Skills for
scaffolding agents with Amazon Bedrock AgentCore, connecting tools, memory,
policies, evaluation, debugging, and production hardening."

Its skills (README, read 2026-10-05): `agents-get-started`, `agents-build`,
`agents-connect` (gateways, tools, Cedar policy), `agents-deploy`,
`agents-debug`, `agents-optimize` (evaluation, observability, traces, cost),
`agents-harden` (production checklist, cold start), `agents-pay`. It uses the
`awsknowledge` MCP server for documentation, and requires the AgentCore CLI
v0.9.0+, the AWS CLI, Node.js 20+ and Python 3.11+ with `uv`.

Its `agents-connect` skill drives `agentcore add gateway` and
`agentcore deploy` and does not mention Terraform.

## What this plugin adds, and does not duplicate

| Need | `aws-agents` | this plugin |
|---|---|---|
| greenfield agent with the AgentCore CLI | yes — use it | not covered; points there |
| deterministic discovery of an existing repo | guidance | `discover.py` with file:line evidence |
| static review with stable ids before deploy | checklist prose | `review.py`, `ACR0xx`, exit codes for CI |
| Terraform for gateway, identity, runtime, memory, observability, budgets | no | yes, with write plans and dry runs |
| a gateway in front of an existing Lambda/HTTP/MCP service | CLI-oriented | target decision, Cognito wiring through module outputs, revision pinning |
| post-deploy verification as a script | guidance | `verify.py` (both MCP eras, p50/p95 vs budget) |
| offline cost estimate from a usage profile | guidance | `cost_estimate.py`, every line's formula |
| trace export to per-segment p50/p95 | guidance | `trace_report.py` |
| plan-only CI with policy gates | no | `gen_ci.py`, `policy_check.py` |

Recommend `aws-agents` when the user is starting a new agent and is happy to
let the AgentCore CLI own the infrastructure. Use this plugin when the
infrastructure is (or will be) Terraform, when something already exists, or
when the answer has to be checkable by a script.

## The AgentCore CLI (`@aws/agentcore`)

`npm install -g @aws/agentcore` (Node.js 20+). Commands: `create`, `dev`,
`deploy`, `invoke`, `add` (agents, memory, credentials, gateways, evaluators,
and more), `remove`, `logs`, `traces`, `status`, and evaluation runs. It keeps
its resources in `agentcore.json` and deploys them through CDK constructs from
`@aws/agentcore-cdk`. The Python `bedrock-agentcore-starter-toolkit` (latest
0.3.13, 2026-09-15) states that its CLI is no longer supported and points to
this CLI. Discovery reports either one, and the review flags the starter
toolkit (`ACR095`).

Sources: https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/.claude-plugin/marketplace.json,
https://raw.githubusercontent.com/aws/agent-toolkit-for-aws/main/plugins/aws-agents/README.md,
https://raw.githubusercontent.com/aws/agent-toolkit-for-aws/main/plugins/aws-agents/skills/agents-connect/SKILL.md,
https://github.com/aws/agentcore-cli, https://pypi.org/project/bedrock-agentcore-starter-toolkit/,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/develop-agents.html (all read 2026-10-05).
