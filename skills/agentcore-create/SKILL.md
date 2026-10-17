---
name: agentcore-create
description: >-
  Scaffold Amazon Bedrock AgentCore resources as infrastructure as code:
  a Runtime (ECR repository, service role, `aws_bedrockagentcore_agent_runtime`
  with a JWT authorizer and lifecycle settings), a Gateway (role, JWT
  authorizer, pinned MCP revisions, one target), Identity (Cognito M2M client
  plus an OAuth2 credential provider with write-only secrets) or Memory
  (memory, strategies, customer-managed key). Terraform modules are the
  default and the recommendation; a TypeScript CDK stack with the
  `aws-bedrockagentcore` L1 constructs and the AgentCore CLI (`@aws/agentcore`)
  commands are offered for teams already on them. Every write is shown as a
  plan first (`--dry-run`), existing files are never overwritten without
  `--force`, and nothing is planned or applied. Use when asked to "create an
  AgentCore runtime", "scaffold a gateway", "add AgentCore memory", "write the
  Terraform for AgentCore", "start a new AgentCore stack", or "give me the CDK
  for this". Don't use for a gateway in front of an existing Lambda, HTTP API
  or MCP server (use `/agentcore:agentcore-gateway`, which resolves the
  upstream and the Cognito wiring), for identity recipes in depth (use
  `/agentcore:agentcore-identity`), or to deploy (use
  `/agentcore:agentcore-deploy`).
argument-hint: "[project-dir] --component runtime|gateway|identity|memory"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# Create AgentCore resources as IaC

A new AgentCore resource should arrive as a reviewed module in the same tree
as everything else the team deploys, not as a console click nobody can
reproduce. This skill writes small, flat Terraform modules — one `main.tf`,
`variables.tf`, `outputs.tf`, `versions.tf` — that the user wires from their
root module. The modules are deliberately boring: every argument is
explained in a comment, secrets are write-only, and the gateway is never
created without an authorizer.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover** first, so the module lands next to the existing ones and the
   region is known:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-discover/scripts/discover.py <project> --focus agentcore,region,terraform
   ```

   If the AgentCore CLI or CDK already owns AgentCore resources (`DSC004`
   territory), offer the matching `--iac` instead of Terraform.

2. **Plan the write.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/scaffold.py <project> --component runtime --dry-run
   ```

   `--component gateway|identity|memory`, `--iac terraform|cdk|cli`,
   `--name`, `--out-dir`, `--protocol HTTP|MCP|A2A|AGUI` (runtime).

3. **Options.** Terraform module (recommended, free), CDK stack (free), or the
   AgentCore CLI commands (free to print; `agentcore deploy` itself is `aws`).

4. **Confirm** with `AskUserQuestion`, then run the same command without
   `--dry-run`. Pass `--force` only when the user asked to replace a file
   after seeing the plan.

5. **Verify.** Run the review on the result and show it:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-review/scripts/review.py <project>
   ```

## Decision rules

- **Terraform first.** It is what the first user runs, and the only option
  where this plugin's review, deploy plan and CI policy all apply. The
  hashicorp/aws provider covers every core resource; see
  [provider-coverage.md](references/provider-coverage.md) for what needs
  `awscc` or the CLI.
- **A module is wired, not applied.** The script prints the `module` block to
  add; it never edits the root module.
- **Write-only secrets need Terraform 1.11+.** The generated `versions.tf`
  says so; older Terraform must use a sensitive variable and accept that the
  secret is in state (`ACR031`).
- **The starter toolkit is not offered.** Its CLI is no longer supported; the
  AgentCore CLI is the CLI alternative.

## References

| Question | File |
|---|---|
| What each generated module contains and why | [terraform-modules.md](references/terraform-modules.md) |
| The CDK and AgentCore CLI paths, and when to choose them | [cdk-and-cli-alternatives.md](references/cdk-and-cli-alternatives.md) |
| Which resources hashicorp/aws covers; `awscc` and CLI fallbacks | [provider-coverage.md](references/provider-coverage.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/scaffold.py <project> --component C [--iac terraform\|cdk\|cli] [--dry-run] [--force] [--json]` | plans and writes a module, a CDK stack, or prints CLI commands | 0 written/planned, 1 nothing to write, 2 bad arguments |

## Completion checklist

- [ ] Discovery ran, and the chosen IaC matches whoever already owns AgentCore resources.
- [ ] The write plan was shown from `--dry-run` and confirmed before writing.
- [ ] The `module` wiring block was given to the user, not written into their root module.
- [ ] `review.py` ran on the result and its findings were shown.
