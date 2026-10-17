#!/usr/bin/env python3
"""Generate a monthly AWS Budget for AgentCore and a usage alarm, as Terraform.

A budget catches money after the fact (Budgets data lags by hours); a
CloudWatch alarm on the gateway's Invocations metric catches a runaway client
within the hour. This writes both: an aws_budgets_budget filtered to the
Bedrock AgentCore service with forecast (80%) and actual (100%) notifications,
and an alarm on AWS/Bedrock-AgentCore Invocations above the hourly volume
your profile implies (x3 headroom). If the project already has an SNS alarm
topic it is offered as the notification target.

    gen_budget.py <project> --monthly-usd 20 [--email you@example.com ...]
                  [--profile profile.json] [--out-dir DIR] [--dry-run] [--force] [--json]

Applying it creates a budget and an alarm, each billed at the AWS Budgets
and CloudWatch alarm prices on their own pricing pages (not modelled here).
Exit codes: 0 planned/written, 1 nothing to write, 2 bad arguments.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DOCS_CHECKED, cli, tfgen  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.templating import WritePlan  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--monthly-usd", type=float, required=True)
    parser.add_argument("--email", action="append", default=[])
    parser.add_argument("--profile", help="usage profile; sets the invocations alarm threshold")
    parser.add_argument("--name", default=None)
    parser.add_argument("--out-dir", default=None)
    cli.add_writer(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir() or args.monthly_usd <= 0:
        print("error: need an existing project directory and a positive --monthly-usd", file=sys.stderr)
        return EXIT_USAGE
    threshold = None
    if args.profile:
        try:
            profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"error: --profile: {exc}", file=sys.stderr)
            return EXIT_USAGE
        gw = profile.get("gateway") or {}
        per_day = float(gw.get("requests_per_day", 0)) * (float(gw.get("tool_calls_per_request", 1)) +
                                                          float(gw.get("list_calls_per_request", 0)))
        threshold = max(10, int(per_day / 24 * 3)) if per_day else None
    project = load(root)
    report = GapReport(subject=str(project.root), skill="agentcore-cost")
    budgets = project.tf.resources_of("aws_budgets_budget")
    topics = project.tf.resources_of("aws_sns_topic")
    if budgets:
        report.add("CST010", "info", "budget", f"the project already has {len(budgets)} budget(s): "
                   f"{', '.join(b.address for b in budgets)}",
                   fix="this one is filtered to AgentCore only, so it does not replace an account-wide budget.")
    name = args.name or tfgen.aws_name(root.resolve().name)
    files = tfgen.budget_module(name=name, monthly_usd=args.monthly_usd, emails=args.email, checked=DOCS_CHECKED,
                                gateway_invocations_alarm=threshold)
    plan = WritePlan()
    out = cli.module_dir(root, args.out_dir, "agentcore-budget")
    for rel, content in files.items():
        plan.add(out / rel, content, force=args.force)
    report.discovered = {"monthly_usd": args.monthly_usd, "alarm_threshold_per_hour": threshold,
                         "sns_topics": [t.address for t in topics]}
    notes = []
    if topics:
        notes.append(f"pass alarm_topic_arn = {topics[0].address}.arn (its policy must allow budgets.amazonaws.com)")
    notes.append("confirm the Cost Explorer service name for AgentCore once the first charge posts")
    return cli.finish_plan(plan, fmt=args.format, dry_run=args.dry_run, report=report, notes=notes)


if __name__ == "__main__":
    raise SystemExit(main())
