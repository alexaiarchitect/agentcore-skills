---
name: agentcore-observe
description: >-
  Make a request's time visible end to end with AWS X-Ray and OpenTelemetry,
  then say where it went. Plans tracing hop by hop: API Gateway (REST APIs
  can trace; HTTP APIs cannot, so the access log carries their share),
  Lambda active tracing plus the ADOT layer for Node.js 24
  (`AWSOpenTelemetryDistroJs`, `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`)
  so DynamoDB, Secrets Manager and HTTP calls appear as subsegments, AgentCore
  Gateway / Runtime / Memory spans through CloudWatch log delivery
  (APPLICATION_LOGS and TRACES) and CloudWatch Transaction Search, and the
  GenAI observability dashboard. Writes an observability module, a Lambda
  tracing patch and a Transaction Search script after a dry run. Then
  `trace_report.py` turns an exported `batch-get-traces`, `get-trace-summaries`
  or OTel span file into per-segment wall and self time at p50/p95 against a
  budget (default 500 ms), with cold-start share and the owner of the time in
  over-budget requests. Findings are the `OBS0xx` band. Use when asked "add
  X-Ray", "trace my gateway", "where did the time go", "why is p95 over
  500 ms", "ADOT for Node Lambda", "Transaction Search", "GenAI
  observability". Don't use for a live latency probe (use
  `/agentcore:agentcore-verify`), for AgentCore Evaluations (quality, not
  time), or for application logging design.
argument-hint: "[project-dir] | trace_report.py <export.json>"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# Where did the time go?

A latency budget can only be enforced if every hop leaves a segment. In the
first user's stack none does today: the API is an HTTP API (no X-Ray), the
Lambda's tracing mode is `PassThrough`, and no tracer instruments DynamoDB or
Secrets Manager. This skill fixes the visibility first, then reads the traces.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Plan tracing**, read-only:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/tracing_plan.py <project> --dry-run
   ```

   It lists every hop with its tracing state, and plans an observability
   module (log delivery for each AgentCore resource), `transaction-search.sh`,
   and `lambda-tracing.patch.tf.txt` for each function on the request path.

2. **Report** the hops, then `OBS01x` findings. Say plainly which hop cannot
   be traced (an HTTP API) and how its share is measured instead.

3. **Options:** write the module and patch (free); the user runs
   `transaction-search.sh` once per account and region (aws); deploy through
   `/agentcore:agentcore-deploy` (aws). **Confirm** with `AskUserQuestion`.

4. **After traffic flows**, the user exports traces (commands in
   [where-did-the-time-go.md](references/where-did-the-time-go.md)) and you
   summarise them:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/trace_report.py traces.json --budget-ms 500
   ```

5. **Report the answer** as: total p50/p95 vs budget, the segment with the
   largest self time at p95, the owner of the time in over-budget requests,
   cold-start share. Recommend the fix for that segment, not a general one.

## The `OBS0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `OBS001` | **error** | no traces with durations in the export |
| `OBS002` | warn | total p95 over the budget |
| `OBS003` | info | cold starts (Lambda `Initialization`) and their share |
| `OBS004` | info | the largest self time at p95 |
| `OBS005` | warn | traces with no downstream subsegments (instrumentation missing) |
| `OBS006` | info | fewer than 20 traces |
| `OBS010` | info | an HTTP API on the path (cannot be X-Ray traced) |
| `OBS011` | warn | a REST API stage without X-Ray tracing |
| `OBS012` | warn | a request-path Lambda not in `Active` tracing mode |
| `OBS013` | warn | a request-path Node.js Lambda with no ADOT layer or tracer |
| `OBS014` | warn | AgentCore resources without log/trace delivery |
| `OBS015` | info | no AgentCore resource yet; the module takes ARNs as variables |

## Decision rules

- **Self time, not wall time, names the culprit.** An `Invocation` of 400 ms
  whose DynamoDB child took 350 ms is a DynamoDB problem.
- **ADOT, not the X-Ray SDK, for new instrumentation.** The X-Ray SDKs and
  daemon entered maintenance on 2026-02-25; end of support is 2027-02-25.
- **Sample at 100% while measuring a budget**, then lower it; Transaction
  Search indexing is billed.
- **Never log content to measure time.** Span structure is enough; keep
  prompt and tool payloads out of spans unless approved
  (`AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT=true` for non-Runtime agents).

## References

| Question | File |
|---|---|
| The runbook: export, summarise, read, fix | [where-did-the-time-go.md](references/where-did-the-time-go.md) |
| Node.js 24 Lambda: active tracing, ADOT layer, ESM, Powertools | [lambda-node-tracing.md](references/lambda-node-tracing.md) |
| AgentCore spans, log delivery, Transaction Search, GenAI dashboard | [agentcore-observability.md](references/agentcore-observability.md) |
| Trace context across API Gateway, Gateway and Lambda | [trace-propagation.md](references/trace-propagation.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/tracing_plan.py <project> [--name PREFIX] [--out-dir D] [--dry-run] [--force] [--json]` | per-hop tracing state, the module, patch and script | 0 planned/written, 1 nothing, 2 bad arguments |
| `scripts/trace_report.py <export> [--budget-ms B] [--top N] [--json]` | per-segment p50/p95 wall and self time | 0 within budget, 1 over budget or nothing parsed, 2 unreadable |

## Completion checklist

- [ ] Every hop's tracing state was reported, including the ones that cannot be traced.
- [ ] Generated files were shown as a write plan and confirmed; the Lambda patch was left for the user to merge.
- [ ] Transaction Search was described as a one-time `aws` step the user runs.
- [ ] `trace_report.py` ran on a real export, and the answer named one segment and one fix.
