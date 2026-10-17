#!/usr/bin/env python3
"""Summarise exported traces into per-segment p50/p95: where did the time go?

Input is a file you exported — this script calls nothing:

* `aws xray batch-get-traces --trace-ids <ids> > traces.json` (full segment
  trees: Lambda Initialization/Invocation/Overhead, DynamoDB, SecretsManager,
  remote HTTP, AgentCore Gateway spans), or
* `aws xray get-trace-summaries ... > summaries.json` (totals only), or
* OpenTelemetry spans as JSON lines, e.g. a CloudWatch Logs export of the
  `aws/spans` log group Transaction Search writes.

For every segment, subsegment or span name it reports wall time and self time
(wall time minus children) at p50 and p95 across traces, the total request
time against the budget, the cold-start share, and which segments own the
time in the requests that blew the budget. Findings are the OBS0xx band:
OBS001 nothing parsed, OBS002 p95 over budget, OBS003 cold starts, OBS004 the
top self-time owner, OBS005 traces with no downstream subsegments
(instrumentation missing), OBS006 too few traces for a p95.

    trace_report.py <export.json> [--budget-ms 500] [--top 12] [--json]

Exit codes: 0 within budget, 1 p95 over budget or nothing parsed, 2 the file
cannot be read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DEFAULT_BUDGET_MS, cli  # noqa: E402
from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.traces import TraceFormatError, breakdown, load  # noqa: E402

RUNBOOK = "references/where-did-the-time-go.md"


def render_table(rows: list[dict], top: int) -> str:
    lines = ["| segment | kind | traces | wall p50 | wall p95 | self p50 | self p95 |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for row in rows[:top]:
        lines.append(f"| {row['name']} | {row['kind']} | {row['traces']} | {row['wall_p50_ms']} | {row['wall_p95_ms']} "
                     f"| {row['self_p50_ms']} | {row['self_p95_ms']} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("export", help="exported trace file")
    parser.add_argument("--budget-ms", type=float, default=float(DEFAULT_BUDGET_MS))
    parser.add_argument("--top", type=int, default=12)
    cli.add_format(parser)
    args = parser.parse_args(argv)
    path = Path(args.export).expanduser()
    try:
        traces, fmt = load(path)
    except (OSError, TraceFormatError) as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    result = breakdown(traces, budget_ms=args.budget_ms)
    report = GapReport(subject=str(path), skill="agentcore-observe")
    total = result["total"]
    if not traces or not total.get("count"):
        report.add("OBS001", "error", "input", "no traces with a duration were found in the export",
                   fix="widen the time window or check the filter expression; see " + RUNBOOK)
    else:
        if total["p95_ms"] > args.budget_ms:
            owner = result["over_budget_self_ms_mean"][0]["name"] if result["over_budget_self_ms_mean"] else "unknown"
            report.add("OBS002", "warn", "latency",
                       f"p95 {total['p95_ms']} ms exceeds the {args.budget_ms:g} ms budget "
                       f"({total['over_budget']} of {total['count']} traces over)",
                       fix=f"in the over-budget requests the largest self time is in {owner}; start there.")
        cold = result["cold_starts"]
        if cold["traces"]:
            report.add("OBS003", "info", "latency",
                       f"cold starts in {cold['traces']} of {result['traces']} traces ({cold['share_pct']}%), "
                       f"p95 {cold.get('p95_ms')} ms",
                       fix="provisioned concurrency or a smaller bundle for Lambda; session reuse for Runtime.")
        if result["segments"]:
            top = result["segments"][0]
            report.add("OBS004", "info", "latency",
                       f"largest self time at p95: {top['name']} ({top['self_p95_ms']} ms)")
        if result["shallow_traces"]:
            report.add("OBS005", "warn", "instrumentation",
                       f"{result['shallow_traces']} trace(s) have no downstream subsegments: calls to DynamoDB, "
                       "Secrets Manager or HTTP are invisible",
                       fix="add the ADOT layer (AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument) or Powertools Tracer.")
        if total["count"] < 20:
            report.add("OBS006", "info", "sample", f"{total['count']} trace(s): the p95 is effectively the maximum",
                       fix="export at least 20, ideally 100, before judging a budget.")
    report.discovered = {"format": fmt, "traces": result["traces"], "total": total,
                         "cold_starts": result["cold_starts"], "over_budget_owners": result["over_budget_self_ms_mean"]}
    if args.format == "json":
        payload = report.to_dict()
        payload["segments"] = result["segments"]
        print(json.dumps(payload, indent=2))
    else:
        print(report.to_md())
        print("\n## Segments (sorted by self p95, ms)\n")
        print(render_table(result["segments"], args.top))
    if report.has_errors() or (total.get("p95_ms") or 0) > args.budget_ms:
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
