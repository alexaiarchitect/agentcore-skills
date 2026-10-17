---
name: agentcore-discover
description: >-
  Inventory a project for Amazon Bedrock AgentCore work and report before
  advising. Finds existing AgentCore resources and which tool owns them
  (Terraform `aws_bedrockagentcore_*`/`awscc_*`, CDK constructs, the AgentCore
  CLI's `agentcore.json`, the deprecated starter toolkit's
  `.bedrock_agentcore.yaml`, boto3 `bedrock-agentcore` clients, the AgentCore
  Python SDK and `@requires_access_token`), the agent framework (Strands,
  LangGraph, LangChain, Claude Agent SDK, CrewAI, OpenAI Agents, ADK, raw),
  MCP servers and the API Gateway routes and Lambdas behind `/mcp`, Cognito
  pools, clients and JWT authorizers, the AWS region and per-service
  availability there, the hashicorp/aws constraint and lock, Terragrunt, and
  Lambda tracing. Read-only; findings are the `DSC0xx` band. Use when asked
  "what do I have", "is this on AgentCore", "inventory this repo", "which
  region are we in", "is AgentCore available in eu-central-1", "what
  framework is this agent", or before any other AgentCore skill on an
  unfamiliar project. Don't use for judging the configuration (use
  `/agentcore:agentcore-review`), for generating anything (use
  `/agentcore:agentcore-create` or `/agentcore:agentcore-gateway`), or for
  querying a live AWS account (this reads files only).
argument-hint: "[project-dir]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Discover an AgentCore project

Discovery is the pass every other skill trusts. It answers with evidence — a
file and line for every claim — and says "not resolved" when it cannot
answer, because a wrong region or a missed owner makes every later step
wrong: a gateway generated in Terraform for a resource the AgentCore CLI
already owns will fight it on every deploy.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/discover.py <project>
   ```

   `--json` for the structured form; `--focus agentcore,app,auth,region,terraform,tracing`
   to narrow it. Point it at the repository root, not at a subdirectory, so
   module calls and Terragrunt stacks resolve.

2. **Report** the `Found` blocks in this order: AgentCore (doors and
   resources), application (framework, MCP servers, `/mcp` routes and the
   Lambda behind them), auth, region (with the availability row), Terraform
   (constraint, lock, Terragrunt), tracing. Then `Missing`, then findings.

3. **Options.** The report's `Options` section is ordered and has exactly one
   recommendation, each with its cost tier. Read them out; do not invent new
   ones.

4. **Confirm** the next skill with `AskUserQuestion`, then invoke it with
   `Skill`. Discovery itself never writes.

5. **Verify** nothing: discovery has no side effects to check. If the user
   corrects a fact (a region, an owner), re-run with the corrected input
   rather than overriding the report in prose.

## What it looks for

| Question | Evidence it reads | Detail |
|---|---|---|
| Is anything on AgentCore, and who owns it? | `.tf`, CDK sources, `agentcore.json`, `.bedrock_agentcore.yaml`, boto3 calls | [what-discovery-detects.md](references/what-discovery-detects.md) |
| Which framework and MCP server? | imports, decorators, `registerTool`, `FastMCP` | [framework-signatures.md](references/framework-signatures.md) |
| Which region, and what is offered there? | provider blocks, variable defaults, Terragrunt, tfvars | the regions table in `lib/agentcore_skills/data/regions.json` |
| How do tokens work today? | `aws_cognito_*`, `aws_apigatewayv2_authorizer` | [what-discovery-detects.md](references/what-discovery-detects.md) |

## The `DSC0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `DSC001` | **error** | nothing to read: no Terraform, code, container or manifest |
| `DSC002` | warn | no AWS region could be resolved |
| `DSC003` | warn | a starter-toolkit config (its CLI is no longer supported) |
| `DSC004` | warn | AgentCore declared by more than one tool (Terraform, CDK, AgentCore CLI) |
| `DSC005` | warn | a core service is not offered in the resolved region |

## Decision rules

- **The un-aliased provider decides the region.** An aliased `us_east_1`
  provider for CloudFront certificates is listed, never chosen.
- **A route ending in `/mcp` is the MCP endpoint.** The Lambda behind it is
  found through the integration, not by name.
- **Absence is "not found", never "does not exist".** Patterns cannot prove a
  negative in TypeScript; say what was searched.

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/discover.py <project> [--focus ...] [--json]` | the inventory and gap report | 0 nothing blocking, 1 errors, 2 bad target |

## Completion checklist

- [ ] `discover.py` ran against the repository root and its output was shown.
- [ ] The region, its evidence, and the availability row were stated.
- [ ] Every AgentCore owner (Terraform, CDK, AgentCore CLI, toolkit) was named, or "none yet".
- [ ] The recommended option was offered with its cost tier, and the user chose.
