---
name: agentcore-review
description: >-
  Statically review a project's Amazon Bedrock AgentCore setup before it is
  deployed, with stable `ACR0xx` finding ids, file and line, a fix and the
  AgentCore page each rule derives from. Checks region availability per
  service (registry, runtime instances, semantic search are not everywhere),
  gateways without a JWT authorizer or with one that accepts any token,
  discovery URLs missing `/.well-known/openid-configuration`, IAM grants of
  `*` or `service:*` on `Resource "*"`, credentials as Terraform literals or in
  state, credential variables not marked sensitive, `.env` copied into an
  image, no log or TRACES delivery, no Transaction Search, Lambdas behind
  `/mcp` or a gateway target without active tracing or ADOT, HTTP APIs that
  cannot be X-Ray traced, targets without outbound auth, Lambda targets with
  the wrong credential type, plain-http upstreams, Runtime images that are not
  ARM64, missing `/ping`, non-stateless MCP servers, unpinned or unsupported
  MCP revisions, memory expiry and encryption, old provider locks and the
  deprecated starter toolkit. Read-only. Use when asked to "review my
  AgentCore setup", "is this gateway secure", "check the IAM", "what's wrong
  before I deploy", "audit the Terraform", or as a CI gate. Don't use for an
  inventory (use `/agentcore:agentcore-discover`), for the Runtime container
  contract in depth (use `/agentcore:agentcore-runtime`), or for checking a
  saved plan (use `/agentcore:agentcore-ci`'s policy check).
argument-hint: "[project-dir] [--region R]"
allowed-tools: Read, Grep, Glob, AskUserQuestion, Skill, Bash(python3 *)
---

# Review an AgentCore setup

Most AgentCore mistakes are visible in the source before anything is
deployed: a gateway left at `authorizer_type = "NONE"`, an OAuth client
secret typed into Terraform, a Lambda behind the MCP route that will never
start a trace. This review reads the Terraform, code and Dockerfiles, and
reports each defect once, with where it is and what to do.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Review.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/review.py <project>
   ```

   `--env infrastructure/live/<env>` (alias `--root`) reviews one
   Terraform/Terragrunt environment and the local modules it calls (code is
   still scanned from `<project>`); a directory given directly also follows
   its `../../modules` sources. `--region eu-central-1` to check availability
   against a region other than the resolved one; `--fail-on warn` for a
   stricter gate; `--json` to branch on ids.

2. **Report** errors first, then warnings, then notes, each with its file,
   line and source. Say which errors are irreversible as written: a secret
   that reached a repository or state must be rotated, not just deleted
   (`ACR030`, `ACR033`).

3. **Options** from the report: fix the errors (recommended when any exist),
   generate the tracing changes (`/agentcore:agentcore-observe`), re-plan the
   gateway (`/agentcore:agentcore-gateway`). All free.

4. **Confirm** with `AskUserQuestion` before editing anything. Fixes in the
   user's own Terraform are edits they approve one by one, shown as diffs.

5. **Verify.** Re-run `review.py` and show the summary line.

## What gets checked

| Area | Ids | The question |
|---|---|---|
| region | `ACR001`–`ACR003` | is each service offered where it is declared |
| inbound auth | `ACR010`–`ACR015` | who can call the gateway or runtime |
| IAM | `ACR020`–`ACR022` | how much does each role allow |
| secrets | `ACR030`–`ACR033` | is any credential in source, state or an image |
| observability | `ACR040`–`ACR045` | will a slow request leave a trace |
| targets | `ACR050`–`ACR054` | how does the gateway authenticate upstream |
| runtime | `ACR060`–`ACR063` | does the container meet the contract |
| protocol | `ACR070`–`ACR071` | which MCP revisions are pinned |
| memory | `ACR080`–`ACR082` | retention, keys, strategy count |
| tooling | `ACR090`, `ACR095` | provider lock, deprecated toolkit |

Every id, its severity and trigger: [review-checklist.md](references/review-checklist.md).

## Decision rules

- **An unresolved value is not a pass.** When a region or policy comes from a
  module input, the review says so (`ACR003`, notes) rather than guessing.
- **Only the request path is held to tracing rules.** The Lambda behind
  `POST /mcp` and gateway-target Lambdas are; a queue worker is not.
- **An HTTP API is not a defect.** `ACR045` is a note: the hop cannot be
  traced, so its share is read from the access log instead.
- **IAM breadth on a CI deploy role is still breadth.** Report it; the user
  decides whether a deploy role's `service:*` is an accepted risk.

## References

| Question | File |
|---|---|
| Every `ACR` id: severity, trigger, fix | [review-checklist.md](references/review-checklist.md) |
| Least-privilege roles for gateway, runtime and Lambda targets | [iam-least-privilege.md](references/iam-least-privilege.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/review.py <project> [--env DIR] [--region R] [--fail-on error\|warn] [--json]` | the `ACR0xx` review | 0 clean at the chosen level, 1 findings, 2 bad target |

## Completion checklist

- [ ] `review.py` ran and its findings were reported, errors first, with sources.
- [ ] Any credential found in source, state or an image was described as needing rotation.
- [ ] No file was edited without the user confirming that specific change.
- [ ] `review.py` was re-run after fixes and the summary line was shown.
