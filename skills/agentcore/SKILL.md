---
name: agentcore
description: >-
  Entry point for Amazon Bedrock AgentCore work: Runtime, Gateway, Identity,
  Memory, Code Interpreter, Browser, Observability and Evaluations, managed
  IaC-first (Terraform preferred; CDK and the AgentCore CLI as alternatives).
  Runs discovery on the project — existing AgentCore resources and which tool
  owns them, agent framework, MCP servers, Cognito/JWT auth, region and
  per-service availability, hashicorp/aws provider lock, tracing — shows what
  exists and what is missing, then routes to one focused skill with its cost
  tier (free = files only; aws = commands you run against AWS that may create
  billable resources). Use when the user says "agentcore", "bedrock agentcore",
  "put my MCP server behind a gateway", "host my agent on AWS", "AgentCore
  Identity", "AgentCore Memory", "is AgentCore available in eu-central-1",
  "X-Ray for my agent", "what will AgentCore cost", asks what this plugin can
  do, or when the intent spans several of those. Don't use when the request
  already names one task - go straight to `/agentcore:agentcore-discover`,
  `/agentcore:agentcore-create`, `/agentcore:agentcore-review`,
  `/agentcore:agentcore-gateway`, `/agentcore:agentcore-identity`,
  `/agentcore:agentcore-runtime`, `/agentcore:agentcore-memory`,
  `/agentcore:agentcore-deploy`, `/agentcore:agentcore-verify`,
  `/agentcore:agentcore-observe`, `/agentcore:agentcore-cost` or
  `/agentcore:agentcore-ci`. Don't use for Bedrock model invocation, Bedrock
  Agents (the older service), or MCP protocol migration of the server itself.
argument-hint: "[project-dir]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Amazon Bedrock AgentCore — start here

AgentCore is a set of separately billed services that are usually adopted one
at a time: a Gateway in front of tools that already exist, Identity to carry
tokens across it, Runtime to host an agent or MCP server, Memory for state.
The questions that decide the next step are the ones people guess wrong —
which region offers which service, what already exists and who owns it
(Terraform, CDK, the AgentCore CLI, a console click), how inbound tokens are
issued today, and whether any request is traced. So the first step is never
advice: it is discovery.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover.** Run it before saying anything about the project:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-discover/scripts/discover.py <project>
   ```

   `--json` to branch on fields; `--focus region,auth` to narrow it.

2. **Report.** Show the `Found` / `Missing` blocks and any findings as the
   script printed them. Always repeat the region line and the availability
   row for the services the user mentioned.

3. **Options.** Offer the skills from the report's `Options` section with
   their cost tier. Exactly one is recommended. For a free-text request, rank
   the skills deterministically first:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/capabilities.py --intent "<the user's words>"
   ```

4. **Confirm.** Ask with `AskUserQuestion`, then invoke the chosen skill with
   the `Skill` tool. Nothing is written and no command that touches AWS is
   run before that answer. Full protocol:
   [interaction-protocol.md](references/interaction-protocol.md).

## Route by intent

| The user wants | Skill | Cost |
|---|---|---|
| an inventory: what is here, what is on AgentCore, which region | `/agentcore:agentcore-discover` | free |
| a new Runtime, Gateway, Identity or Memory resource as IaC | `/agentcore:agentcore-create` | free |
| a static review before deploying (`ACR0xx`) | `/agentcore:agentcore-review` | free |
| a gateway in front of an existing Lambda, HTTP API or MCP server | `/agentcore:agentcore-gateway` | free |
| inbound JWT from Cognito, outbound credentials, workload identity | `/agentcore:agentcore-identity` | free |
| an agent or MCP server hosted on Runtime; container contract; cold starts | `/agentcore:agentcore-runtime` | free |
| memory resources, strategies, retention, PII | `/agentcore:agentcore-memory` | free |
| the apply sequence, quotas, rollback, the exact commands | `/agentcore:agentcore-deploy` | aws |
| proof it works: tools/list, one call, p50/p95 vs budget | `/agentcore:agentcore-verify` | aws |
| X-Ray / OpenTelemetry end to end; where a request's time goes | `/agentcore:agentcore-observe` | free |
| a monthly estimate from a usage profile; budget alarms | `/agentcore:agentcore-cost` | free |
| plan-only CI with policy gates | `/agentcore:agentcore-ci` | free |

A request that names none of these is usually "put AgentCore in front of what
I have", which starts with `/agentcore:agentcore-gateway` when discovery finds
an MCP endpoint, and with `/agentcore:agentcore-review` when AgentCore
resources already exist.

## Neighbours this plugin does not replace

- **`aws-agents`** (in `anthropics/claude-plugins-official`, sourced from
  `aws/agent-toolkit-for-aws`) guides building agents with the AgentCore CLI
  (`@aws/agentcore`, CDK under the hood). Recommend it for a greenfield agent
  built the CLI way. This plugin adds what it does not have: deterministic
  discovery, review and verification scripts, Terraform generation, an
  offline cost model and trace analysis. See
  [neighbours.md](references/neighbours.md).
- **The AgentCore CLI** owns its own `agentcore.json` and CDK app. Discovery
  reports it; do not generate Terraform for resources it owns.

## Ground rules

- **Never guess the region or what exists.** Run discovery; quote it.
- **Say what a step costs before taking it.** `free` steps read and write
  files; `aws` steps are commands the user runs, which may create billable
  resources or read billable telemetry.
- **Never run `terraform apply`, `terragrunt apply` or a mutating `aws`
  command.** Emit it, explain it, and let the user run it.
- **Cite the page.** Every finding carries a `Source:`; repeat it when you
  explain a behaviour. Facts were checked on the date in
  [finding-bands.md](references/finding-bands.md).

## References

| Question | File |
|---|---|
| How every skill here behaves, step by step | [interaction-protocol.md](references/interaction-protocol.md) |
| What each skill does, needs and costs | [capability-map.md](references/capability-map.md) |
| Finding-id bands and exit codes | [finding-bands.md](references/finding-bands.md) |
| The official `aws-agents` plugin and the AgentCore CLI | [neighbours.md](references/neighbours.md) |
| What a word means here | [glossary.md](references/glossary.md) |

## Scripts

| Command | Output | Exit codes |
|---|---|---|
| `scripts/capabilities.py [--intent TEXT] [--json]` | the skill table with cost tiers, and a ranked suggestion | 0, 2 skills unreadable |

## Completion checklist

- [ ] Discovery was run and its output shown, not summarised from memory.
- [ ] The region and the availability of the services in question were stated.
- [ ] Options were offered with cost tiers, one recommended, and the user chose.
- [ ] The chosen skill was invoked, not re-implemented here.
