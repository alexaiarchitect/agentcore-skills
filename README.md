# `agentcore` — Claude Code skills for Amazon Bedrock AgentCore

Thirteen skills for creating, reviewing, deploying, verifying, observing and
cost-managing Amazon Bedrock AgentCore resources — Runtime, Gateway, Identity,
Memory, Code Interpreter, Browser, Observability and Evaluations —
infrastructure-as-code first. Checked against the AgentCore developer guide,
pricing, quotas and regions pages **as of 2026-10-05**, and the hashicorp/aws
provider documentation at **6.64.0** (generated Terraform assumes `>= 6.55.0`).

The premise: most AgentCore work is not greenfield. It is putting a gateway in
front of a Lambda that already serves MCP, carrying a Cognito token across it,
and finding out where a request's 500 ms went. Those are decisions with
consequences — which target type, whose identity reaches the upstream, which
MCP revision clients speak, which hop cannot be traced — so every skill here
makes the decision visible, writes Terraform only after you have seen the plan,
and leaves every command that touches AWS for you to run.

## Install

Run these commands inside Claude Code:

```text
/plugin marketplace add alexaiarchitect/agentcore-skills
/plugin install agentcore@alexaiarchitect-agentcore
```

To try a local checkout without installing:

```bash
claude --plugin-dir /path/to/agentcore-skills
```

Then start with `/agentcore:agentcore` in any project, or go straight to the
skill you want.

## The skills

| Skill | Use it to | Cost |
|---|---|---|
| `/agentcore:agentcore` | discover a project and route to the right skill | free |
| `/agentcore:agentcore-discover` | inventory AgentCore resources and their owner (Terraform, CDK, AgentCore CLI, starter toolkit, boto3), framework, MCP routes, Cognito, region availability, provider lock, tracing | free |
| `/agentcore:agentcore-create` | scaffold Runtime, Gateway, Identity or Memory as a Terraform module (or CDK, or AgentCore CLI commands) | free |
| `/agentcore:agentcore-review` | static review, `ACR0xx`: region, JWT authorizer, IAM, secrets, tracing, targets, container contract, MCP revisions, memory | free |
| `/agentcore:agentcore-gateway` | put a gateway in front of an existing Lambda, HTTP API or MCP server; Cognito JWT; revision pinning; tool-name limits | free |
| `/agentcore:agentcore-identity` | inbound JWT from Cognito, outbound credential providers, workload identity, and whether the user's identity survives the hop | free |
| `/agentcore:agentcore-runtime` | host an agent or MCP server on Runtime: ARM64, ports, `/ping`, stateless MCP, sessions and cold starts | free |
| `/agentcore:agentcore-memory` | memory resources, strategies, retention, keys, personal data | free |
| `/agentcore:agentcore-deploy` | apply sequence, quotas, the exact commands, rollback — never run for you | aws |
| `/agentcore:agentcore-verify` | tools/list and a call through the gateway in both MCP eras, p50/p95 vs budget, `/ping`, read-only AWS checks | aws |
| `/agentcore:agentcore-observe` | X-Ray/OpenTelemetry end to end; a trace export summarised into per-segment p50/p95 | free |
| `/agentcore:agentcore-cost` | a monthly estimate from a usage profile, every line's formula; budget and alarm | free |
| `/agentcore:agentcore-ci` | plan-only CI with policy gates against destructive or open changes | free |

## How they behave

Every skill follows the same five steps: **discover** the project with a
script, **report** what it found, **offer options** with their cost, **confirm**
with a question, then **act and verify**. Nothing is written before you
answer, generators always show a write plan from `--dry-run` first, and
existing files are never overwritten without `--force`.

Costs are stated up front as a tier: `free` (reads and writes files, parses
exports, or calls an endpoint you already run) and `aws` (commands you run
against your AWS account; they may create billable resources or read billable
telemetry).

## Four things worth knowing before you start

**AgentCore Gateway speaks MCP 2025-03-26 through 2025-11-25, and 2026-07-28
only if you opt in.** The stateless 2026-07-28 revision is enabled per gateway
through `supportedVersions`; `UpdateGateway` replaces the list rather than
appending; a request with no version header is treated as 2025-03-26; and the
gateway translates ordinary tool calls between eras but not elicitation or
sampling. `agentcore-gateway` pins the list explicitly and `agentcore-verify
--protocol both` proves both work.

**A gateway's outbound token is the gateway's, not your user's.** With client
credentials, an upstream that derives ownership from the token subject sees
one principal for everyone. `agentcore-identity` lays out the options (token
exchange, an interceptor that forwards the user's validated JWT or signs a
claim, an HTTP/Runtime target with passthrough) before anything is generated,
and `gateway_plan.py --interceptor forward-jwt` generates the interceptor.

**An API Gateway HTTP API cannot be X-Ray traced.** Neither can a Lambda in
`PassThrough` mode. `agentcore-observe` turns on what can be traced, measures
the rest from access logs, and reads exported traces into the segment that
owns the time.

**eu-central-1 has every core service** — Runtime (microVMs and Instances),
Gateway (with semantic search), Identity, Memory, built-in tools,
Observability, Evaluations, Policy — but not the Agent Registry or the Web
Search tool. Discovery prints the availability row for your region.

## New in 0.2.0

Fixes for every friction logged on the first real use (see
[CHANGELOG.md](CHANGELOG.md)). Flags that changed:

| Script | New flags / behaviour |
|---|---|
| `gateway_plan.py` | `--interceptor forward-jwt\|signed-claim\|<lambda arn>` and `--meta-key` (interceptor Lambda, IAM and wiring); `--client-ref`; `--out-dir` is the modules directory (gateway, identity and interceptor modules side by side); the gateway role is scoped to workload-identity / token-vault / provider ARNs |
| `review.py` | `--env DIR` (alias `--root`): one Terragrunt environment and the local modules it calls; an environment directory given directly follows `../../modules` sources |
| `deploy_plan.py` | provider constraint, lock, region and stages from the chosen `--root` only; commands use `$AGENTCORE_PLUGIN` |
| `identity_plan.py` | `--client-ref aws_cognito_user_pool_client.x` reuses an existing client (`IDN007`) |
| `tracing_plan.py` | `--name PREFIX`: delivery and log-group names are unique per environment |
| `tool_names.py` | `--target-type mcp\|lambda\|openapi`; a probe report decides which tools count |

## Requirements

Python 3.10+ for the plugin's scripts, which are **standard library only** and
never import an AWS SDK; they read files and print commands. The commands
they print need what you already use: Terraform 1.11+ (write-only secrets) or
Terragrunt, the AWS CLI v2 with credentials for the target account, and Docker
with `buildx` for Runtime images. `verify.py` talks HTTPS to the gateway URL
you name, with a token from an environment variable you name.

## Neighbours

The official **`aws-agents`** plugin (in `anthropics/claude-plugins-official`,
from `aws/agent-toolkit-for-aws`) guides greenfield agents built with the
AgentCore CLI. This plugin adds deterministic discovery, review and
verification scripts, Terraform generation, an offline cost model, trace
analysis and CI gates; it reads an AgentCore CLI project but does not fight it
for ownership.

## Development

```bash
python3 -m pytest -q                                           # the plugin's own tests
claude plugin validate . --strict
claude plugin eval . --scaffold --allow-tools Bash Write Edit --runs 1    # skill-level cases in plugin-evals/
python3 .dev/check_sources.py --tier 1                         # what moved upstream
python3 .dev/sweep.py                                          # run the readers over real projects
```

`.dev/` holds maintainer working notes (the verified-facts ledger, source
watchers and sweep reports) and is not in the repository.

Scripts are exercised as subprocesses, the way a skill runs them. The verify
tests run a fake gateway on 127.0.0.1; nothing in the suite needs AWS,
credentials or the internet.

## Attribution

AgentCore behaviour is cited from the Amazon Bedrock AgentCore documentation
at `docs.aws.amazon.com/bedrock-agentcore`, the AgentCore pricing page and AWS
blogs; Terraform arguments from `hashicorp/terraform-provider-aws` (MPL-2.0).
See `THIRD_PARTY_NOTICES.md` for every source consulted. Fixtures are original
and synthetic, except `tests/fixtures/projects/vault_envs`, which is derived
from the first user's own Terraform with every name, domain and account id
replaced; nothing from a non-redistributable source is included.
