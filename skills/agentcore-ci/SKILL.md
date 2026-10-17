---
name: agentcore-ci
description: >-
  Put Amazon Bedrock AgentCore infrastructure behind a plan-only CI gate.
  Generates a GitHub Actions workflow that, on pull requests touching the
  infrastructure, runs the static AgentCore review (`ACR0xx`), `terraform fmt
  -check`, `init`, `validate`, a saved `plan` (Terraform or Terragrunt) with a
  read-only OIDC role, `show -json`, and the plan policy (`CI0xx`: no delete or
  replace of memories, gateways, credential providers, workload identities,
  user pools or tables without an explicit per-address allowance; no `*` on
  `*`; no gateway with `authorizer_type = NONE`; pinned MCP revisions), then
  uploads the plan JSON. Nothing in it applies. The plugin's stdlib-only
  library is vendored into `ci/agentcore/` so the job needs nothing from the
  plugin, and action pins are reused from the repository's own SHA-pinned
  workflows. `policy_check.py` also runs locally on any saved plan. Use when
  asked to "add CI for the AgentCore Terraform", "gate the plan", "block
  destructive changes", "policy check the plan", "plan on pull requests".
  Don't use to deploy from CI (apply stays a reviewed human step through
  `/agentcore:agentcore-deploy`), for application CI, or for evaluating the
  agent's behaviour.
argument-hint: "[project-dir] [--tf-root DIR] | policy_check.py <plan.json>"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# Plan-only CI with policy gates

The expensive AgentCore mistakes are visible in a plan: a memory that would
be replaced (every conversation gone), a gateway that would be replaced (a
new URL for every client), a role that grants everything. A pull request is
the cheapest place to stop them, and a plan is the right artefact to check —
it is what would actually happen.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Plan the workflow**, read-only:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gen_ci.py <project> --dry-run
   ```

   `--tf-root` for the stack to plan (default: the root that reaches the
   AgentCore resources), `--role-var` for the GitHub variable holding the
   plan role (default `AWS_PLAN_ROLE_ARN`), `--region`, `--terraform`.

2. **Report** the root, Terraform or Terragrunt, the pins found (or `CI010`
   if the fallbacks are used), and the role note (`CI011`).

3. **Options:** write the workflow and vendored checker (free); run the
   policy on an existing saved plan first (free). **Confirm** with
   `AskUserQuestion`, then write.

4. **Try the gate locally** on a plan the user produced:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/policy_check.py agentcore.plan.json
   ```

   `--allow-replace <address>` only for a replacement a human has reviewed.

5. **Verify** the vendored runner works from the repository root:
   `python3 ci/agentcore/run.py review .`.

## The `CI0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `CI001` | **error** | the plan deletes or replaces a memory, gateway, credential provider, workload identity, Cognito user pool or DynamoDB table |
| `CI002` | **error** | a planned IAM policy allows `*` on `*` |
| `CI003` | **error** | a gateway planned with `authorizer_type = "NONE"` |
| `CI004` | warn | a gateway planned without `supported_versions` |
| `CI005` | info | the plan has no changes |
| `CI006` | info | the AgentCore resources the plan creates (the billing surface) |
| `CI010` | info | no SHA-pinned actions in the repository; fallback pins used |
| `CI011` | info | the plan job's role must be read-only |

## Decision rules

- **CI plans; humans apply.** The workflow has no apply job, and the plan
  role should not be able to write.
- **Allowances are per address.** `--allow-replace` names one resource; there
  is no "allow all".
- **Pin actions to SHAs.** Reuse the repository's pins; the fallbacks are the
  ones the first user's repository carried on 2026-10-05, labelled with tags.
- **Vendored, not installed.** `ci/agentcore/` is plain Python 3.10+; updating
  the plugin means re-running `gen_ci.py --force` and reviewing the diff.

## References

| Question | File |
|---|---|
| The workflow, step by step; roles; Terragrunt | [plan-only-ci.md](references/plan-only-ci.md) |
| Each policy rule, why, and how to allow a reviewed exception | [policy-gates.md](references/policy-gates.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/gen_ci.py <project> [--tf-root D] [--role-var V] [--dry-run] [--force] [--json]` | the workflow plus `ci/agentcore/` | 0 written/planned, 1 nothing, 2 bad arguments |
| `scripts/policy_check.py <plan.json> [--allow-replace ADDR ...] [--json]` | the `CI0xx` gate on a saved plan | 0 pass, 1 policy error, 2 not a plan |

## Completion checklist

- [ ] The workflow was shown as a write plan and confirmed before writing.
- [ ] It has no apply step, and the plan role was described as read-only.
- [ ] `policy_check.py` was run on a real plan, or the user was told how.
- [ ] The vendored runner was exercised from the repository root.
