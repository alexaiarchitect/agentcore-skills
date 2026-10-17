---
name: agentcore-memory
description: >-
  Plan Amazon Bedrock AgentCore Memory: short-term memory (raw session events,
  kept 7 to 365 days) and long-term memory (records extracted by strategies —
  SEMANTIC facts, SUMMARIZATION, USER_PREFERENCE, EPISODIC, or custom — scoped
  by namespace templates such as `facts/{actorId}`), at most six strategies
  and one of each built-in type per memory, encryption with a customer-managed
  KMS key, and what personal data means for retention and erasure. Reads
  existing `aws_bedrockagentcore_memory` resources and SDK usage, checks the
  requested settings (`MEM0xx`), and writes a Terraform module after a dry
  run; refuses to write invalid settings. Use when asked to "add memory to my
  agent", "remember users across sessions", "which memory strategy", "how
  long is memory kept", "is memory encrypted", "GDPR and agent memory", or
  "AgentCore Memory Terraform". Don't use for Runtime session storage (files
  across stop/resume; see `/agentcore:agentcore-runtime`), for vector stores
  or knowledge bases outside AgentCore, or for the memory bill alone (use
  `/agentcore:agentcore-cost`).
argument-hint: "[project-dir] [--strategies SEMANTIC,...] [--expiry-days N]"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# AgentCore Memory

Memory is where an agent's conversations outlive the microVM that held them,
which makes it the one AgentCore resource that is mostly personal data.
Decide retention, scoping and keys when the memory is created; changing them
later means migrating records.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover** existing memories and memory usage in code:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-discover/scripts/discover.py <project> --focus agentcore,region
   ```

2. **Plan**, read-only:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/memory_plan.py <project> --strategies SEMANTIC,SUMMARIZATION --expiry-days 30 --pii --dry-run
   ```

   `--kms` is the default; `--no-kms` uses an AWS-managed key. `--pii` adds
   the retention and erasure notes.

3. **Report** `MEM` findings. Errors stop the plan: nothing is written while
   a setting is out of range.

4. **Options:** the module as planned (free); a different strategy set; cost
   first (`/agentcore:agentcore-cost`, free). **Confirm** with
   `AskUserQuestion`, then write.

5. **Verify** with `review.py` (`ACR080`–`ACR082` cover memory).

## The `MEM0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `MEM001` | **error** | expiry outside 7–365 days |
| `MEM002` | **error** | an unknown or CUSTOM strategy type (CUSTOM needs a configuration this generator does not write) |
| `MEM003` | **error** | a built-in type listed twice |
| `MEM004` | **error** | more than six strategies |
| `MEM005` | warn | personal data without a customer-managed key |
| `MEM006` | info | retention and erasure notes for personal data |
| `MEM007` | info | USER_PREFERENCE without `--pii` |

## Decision rules

- **Scope by actor.** Namespace templates start with `{actorId}`-scoped
  paths so one user's records are never retrieved for another.
- **Nothing sensitive in event metadata.** It is not encrypted with the
  customer-managed key.
- **Expiry is for raw events.** Extracted long-term records persist until
  deleted; erasure means deleting both.
- **Do not assume read-your-writes for long-term records.** Strategies run on
  events after they are written; measure before relying on a record in the
  next turn.

## References

| Question | File |
|---|---|
| Short- vs long-term, events, sessions, actors | [memory-model.md](references/memory-model.md) |
| The strategy types and namespace templates | [strategies-and-namespaces.md](references/strategies-and-namespaces.md) |
| Retention, keys, personal data, erasure; quotas and price | [retention-and-pii.md](references/retention-and-pii.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/memory_plan.py <project> [--strategies ...] [--expiry-days N] [--kms\|--no-kms] [--pii] [--dry-run] [--force] [--json]` | `MEM` findings and the module | 0 planned/written, 1 error (nothing written), 2 bad arguments |

## Completion checklist

- [ ] Existing memories were listed before planning a new one.
- [ ] Expiry, strategies and key choice were stated and confirmed.
- [ ] For personal data, retention and erasure were discussed (`MEM006`).
- [ ] The write plan was confirmed before writing; `review.py` re-run.
