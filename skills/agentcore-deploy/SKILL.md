---
name: agentcore-deploy
description: >-
  Plan the deployment of Amazon Bedrock AgentCore infrastructure and its
  rollback, and hand the user the exact commands — never running them. Finds
  the root module (or Terragrunt stack) that actually reaches the AgentCore
  resources, orders what comes up (identity and roles, then gateway, runtime
  and memory, then targets and strategies, then log delivery), flags where a
  first apply trips (IAM propagation, creation-only semantic search,
  Transaction Search before TRACES delivery, an old provider lock, no remote
  backend), checks published quotas (targets per gateway, tools per target),
  and emits init / validate / plan-to-file / show -json / policy check / apply
  of that saved plan, the post-apply checks, and the rollback for each kind of
  change. Findings are the `DPL0xx` band; the cost tier is `aws` because the
  commands create billable resources. Use when asked to "deploy the gateway",
  "apply this", "what order do I apply in", "how do I roll back", "will this
  hit a quota", "give me the terraform commands". Don't use for generating the
  Terraform (use `/agentcore:agentcore-create` or
  `/agentcore:agentcore-gateway`), for checking after the apply (use
  `/agentcore:agentcore-verify`), or for CI (use `/agentcore:agentcore-ci`).
argument-hint: "[project-dir] [--root DIR]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Deploying AgentCore: sequence, quotas, commands, rollback

The deploy is where this plugin stops acting and starts advising. Terraform
already orders resources by their references; what it cannot tell you is
which root to plan, what will fail on a first apply for reasons outside the
graph, which settings cannot be changed later, and how to get back. This
skill writes nothing and runs nothing: it prints the commands, and the user
runs them.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Review first.** A deploy plan on top of an error is a plan to deploy the
   error:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-review/scripts/review.py <project>
   ```

2. **Plan the deploy.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/deploy_plan.py <project>
   ```

   `--root DIR` when the discovered root is not the one to deploy (provider
   constraint, lock, region and stages are then that root's own);
   `--plan-file NAME`; `--json`. Commands name the plugin as
   `$AGENTCORE_PLUGIN`, set by the printed `setup` line.

3. **Report** the root module, the stages, the `DPL` findings, the commands
   and the rollback, in that order. State the cost tier: these commands
   create billable resources in the user's account.

4. **Options:** (1, recommended) the user runs init → validate → plan to a
   file → `show -json` → the policy check, and pastes the policy output;
   (2) after reading it, the user applies **that saved plan file**. Confirm
   each with `AskUserQuestion`; never collapse them into one step.

5. **Verify** after the user reports a successful apply: hand over to
   `/agentcore:agentcore-verify`.

## The `DPL0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `DPL001` | warn | no remote backend (and no Terragrunt) |
| `DPL002` | **error** | a published quota exceeded (targets per gateway, tools per target) |
| `DPL003` | info | role and gateway in one apply: IAM propagation may fail the first try |
| `DPL004` | info | semantic search is creation-only |
| `DPL005` | info | a Terragrunt stack: commands use `terragrunt` |
| `DPL006` | warn | hashicorp/aws locked below 6.55.0 |
| `DPL007` | info | TRACES delivery needs Transaction Search enabled first |
| `DPL008` | info | the chosen root declares no hashicorp/aws version constraint |

## Decision rules

- **Apply a saved plan, never `-auto-approve`.** The plan the user read is the
  plan that runs.
- **Policy before apply.** `policy_check.py` refuses deletes of memories,
  gateways, credential providers and user pools without an explicit
  `--allow-replace`.
- **`-target` is for rollback, not for the first deploy.** If the first
  apply fails on IAM propagation, re-run the same apply.
- **Roll back by reverting, not by destroying.** Stateful resources (users,
  conversations, secrets) are never part of a rollback.

## References

| Question | File |
|---|---|
| Stage order, what trips first applies, Terragrunt | [apply-sequencing.md](references/apply-sequencing.md) |
| The AgentCore quotas that matter at deploy time | [quotas.md](references/quotas.md) |
| Rollback per kind of change; what never to destroy | [rollback.md](references/rollback.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/deploy_plan.py <project> [--root DIR] [--plan-file F] [--json]` | root, stages, `DPL` findings, commands, rollback | 0 no errors, 1 errors, 2 no Terraform |

## Completion checklist

- [ ] `review.py` ran first and its errors were resolved or accepted by the user.
- [ ] `deploy_plan.py` ran; the root module was confirmed with the user.
- [ ] The cost tier (`aws`) was stated before any command was handed over.
- [ ] The user ran plan → show -json → policy check before any apply.
- [ ] Only the saved plan file was applied, by the user; no command was run by the assistant.
- [ ] The rollback for this change was stated before the apply.
