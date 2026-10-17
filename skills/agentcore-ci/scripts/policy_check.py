#!/usr/bin/env python3
"""Gate a Terraform plan on the AgentCore plan policy (the CI0xx band).

Run it on the JSON form of a saved plan:

    terraform plan -out=agentcore.tfplan
    terraform show -json agentcore.tfplan > agentcore.plan.json
    policy_check.py agentcore.plan.json [--allow-replace ADDRESS ...] [--json]

It refuses (exit 1) a plan that deletes or replaces something that holds
state or identity — an AgentCore Memory, a gateway (its URL is what every
client is configured with), a credential provider, a workload identity, a
Cognito user pool, a DynamoDB table — unless that exact address is passed to
--allow-replace after a human has read the plan; and a plan that grants * on
* or creates a gateway with authorizer_type NONE. It warns on a gateway with
no pinned MCP supported_versions, and lists the AgentCore resources the plan
creates so a reviewer sees the billing surface. It reads a file and calls
nothing; the same logic is vendored into CI by gen_ci.py.

Exit codes: 0 pass, 1 a policy error, 2 not a readable plan.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import cli  # noqa: E402
from agentcore_skills.plan_policy import PlanError, check, render_md  # noqa: E402
from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("plan", help="output of `terraform show -json <planfile>`")
    parser.add_argument("--allow-replace", action="append", default=[], metavar="ADDRESS")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    try:
        plan = json.loads(Path(args.plan).expanduser().read_text(encoding="utf-8"))
        result = check(plan, allow_replace=tuple(args.allow_replace))
    except (OSError, ValueError, PlanError) as exc:
        print(f"error: {args.plan}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(result, indent=2) if args.format == "json" else render_md(result))
    return EXIT_FINDINGS if result["summary"]["errors"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
