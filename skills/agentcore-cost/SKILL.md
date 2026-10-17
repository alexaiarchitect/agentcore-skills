---
name: agentcore-cost
description: >-
  Estimate what Amazon Bedrock AgentCore will cost per month from a usage
  profile, line by line with the formula for each line, and put a budget and
  a usage alarm around it. Prices the published AgentCore rate card (Gateway
  invocations, search and tool indexing; Identity token requests, free
  through Runtime or Gateway; Runtime vCPU-hours billed only while active and
  GB-hours; Memory short-term events — per 1,000 events until 2026-10-05, per
  GB from 2026-10-06 — and long-term records and retrievals; Evaluations
  tokens), prices model tokens only at the user's own per-1,000 rates, and
  lists what it does not price (Lambda, API Gateway, CloudWatch, X-Ray,
  DynamoDB) so the total is never mistaken for the bill. Generates an AWS
  Budget filtered to AgentCore with forecast and actual alerts, plus a
  CloudWatch alarm on gateway invocations, as Terraform after a dry run.
  Findings are the `CST0xx` band. Use when asked "what will AgentCore cost",
  "estimate the gateway bill", "is there a free tier", "memory pricing
  change", "set a budget alarm", "how much per 1,000 requests". Don't use for
  the AWS bill of non-AgentCore services in depth, for Savings Plans or
  committed-use decisions, or for live Cost Explorer queries.
argument-hint: "<profile.json> | gen_budget.py <project> --monthly-usd N"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# What will AgentCore cost?

AgentCore bills each service on its own dimension, and the services a
gateway-fronted Lambda uses most (Lambda, API Gateway, CloudWatch, X-Ray) are
not AgentCore at all. So an honest estimate prices exactly what the AgentCore
rate card covers, shows its arithmetic, and lists what is left out.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Build a profile** with the user. Start from the example and ask for the
   numbers that drive cost: requests per day, tool calls per request, Runtime
   sessions and their length, Memory events and records. Fields:
   [usage-profile.md](references/usage-profile.md).

   ```bash
   cp ${CLAUDE_SKILL_DIR}/assets/profile.example.json ./agentcore-profile.json
   ```

   Writing the profile is a file write: confirm it first.

2. **Estimate.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/cost_estimate.py agentcore-profile.json
   ```

   `--as-of 2026-10-06` to apply the new Memory rate card; `--json` for the
   lines.

3. **Report** the total as "AgentCore lines only", the per-service split, the
   largest line and its formula, and the unpriced list. Quote the pricing
   source and its checked date; every figure is a list-price estimate.

4. **Options:** a budget and alarm module (free to generate); a cheaper
   design for the largest line (e.g. no semantic search, fewer memory
   strategies); nothing. **Confirm** with `AskUserQuestion`, then:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gen_budget.py <project> --monthly-usd 20 --email ops@example.com --profile agentcore-profile.json --dry-run
   ```

5. **Verify** with `review.py` on the project after writing.

## The `CST0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `CST001` | warn | the profile's region does not offer Gateway |
| `CST002` | info | what is not priced (always listed) |
| `CST003` | info | Memory priced on the per-event card that ends 2026-10-05 |
| `CST004` | warn | the rate card is more than 90 days older than `--as-of` |
| `CST005` | info | the page publishes one rate card, not per-region prices |
| `CST010` | info | the project already has budgets |

## Decision rules

- **Never call the total "the bill".** It is the AgentCore lines at list
  price.
- **Model tokens are the user's numbers.** Bedrock model prices vary by model
  and region; the profile supplies them or they are left out.
- **Identity through Runtime or Gateway is free**; outside them it is
  $0.010 per 1,000 requests.
- **Alarms beat budgets for runaways.** Budgets lag by hours; an invocation
  alarm fires within the hour.

## References

| Question | File |
|---|---|
| Every pricing dimension, with the rate and its date | [pricing-dimensions.md](references/pricing-dimensions.md) |
| The profile format, field by field | [usage-profile.md](references/usage-profile.md) |
| The budget and alarm module | [budget-alarms.md](references/budget-alarms.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/cost_estimate.py <profile.json> [--as-of DATE] [--json]` | the line-by-line estimate | 0 estimated, 2 bad profile |
| `scripts/gen_budget.py <project> --monthly-usd N [--email E] [--profile P] [--dry-run] [--force] [--json]` | budget + invocation alarm module | 0 planned/written, 1 nothing, 2 bad arguments |

## Completion checklist

- [ ] The profile's numbers came from the user, and the file was written only after confirmation.
- [ ] The estimate was reported as AgentCore lines only, with the unpriced list.
- [ ] The pricing source and checked date were quoted; Memory's rate-card date was applied.
- [ ] Any budget module was shown as a write plan and confirmed before writing.
