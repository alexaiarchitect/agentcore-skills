# Interaction protocol

Every skill in this plugin follows the same five steps. They exist because
AgentCore work mixes two very different kinds of action — editing files in a
repository, and creating billable, sometimes stateful resources in an AWS
account — and the user must always know which one is about to happen.

## 1. Discover

Run the skill's script against the project before giving any advice. The
script reads files only: Terraform (`.tf`, `.terraform.lock.hcl`,
`terragrunt.hcl`), application code (Python by `ast`, TypeScript and
JavaScript by pattern), Dockerfiles, `package.json`, `requirements.txt`,
`agentcore.json` and `.bedrock_agentcore.yaml`. It never imports the code it
reads and never calls AWS.

## 2. Report

Show what the script printed: `Found`, `Missing`, then findings by severity
(errors, warnings, notes). Do not paraphrase numbers, ids or file paths; they
are the evidence for every option that follows. When a value could not be
resolved (a region behind a module input, a policy built elsewhere) say so —
"not resolved" is an answer, a guess is not.

## 3. Options, each with a cost tier

| Tier | Meaning |
|---|---|
| `free` | reads files, writes files after confirmation, parses an export, or calls an endpoint the user already runs (a local container, a gateway URL with their own token) |
| `aws` | the step is one or more commands the user runs against their AWS account; it may create billable resources (`terraform apply`) or read billable telemetry (`aws xray get-trace-summaries`) |

Exactly one option is recommended. The recommendation follows from the
findings: an error-level finding is fixed before anything is generated on top
of it.

## 4. Confirm

Ask with `AskUserQuestion`. Offer the options as the choices, with the
recommended one first. Nothing is written before the answer — generators are
run with `--dry-run` first so the write plan can be shown, then run again
without it.

## 5. Act and verify

Write what was confirmed, then re-run the checking script (review, runtime
check, tracing plan) on the result and show that it came back clean, or show
what is left. Commands that touch AWS are printed in a fenced block for the
user to run; when they have run them, read the output they paste back (a plan
JSON, a trace export) with the matching script.

## What never happens

- `terraform apply`, `terragrunt apply`, `cdk deploy`, `agentcore deploy` or
  any mutating `aws` command run by the assistant.
- A secret written into a file: generators use write-only Terraform arguments
  (`client_secret_wo`, `api_key_wo`) and sensitive variables, and the verify
  script reads tokens from an environment variable the user names.
- An existing file overwritten without `--force`, which is only passed when
  the user asked for it after seeing the diff.

Sources: plugin conventions shared with `claude-agent-sdk-skills`
(`skills/agent-sdk/references/interaction-protocol.md`); AgentCore developer
guide, https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/ (read
2026-10-05).
