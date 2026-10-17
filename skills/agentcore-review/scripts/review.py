#!/usr/bin/env python3
"""Statically review a project's AgentCore setup: the ACR0xx band.

What this catches before anything is deployed, each with the file and line
and the AgentCore page the rule comes from:

* ACR00x a resource in a region that does not offer its service
* ACR01x a gateway with no JWT authorizer, a malformed discovery URL, or a
  JWT authorizer that accepts any token the issuer signs
* ACR02x IAM grants of * (or service:*) on Resource "*"
* ACR03x credentials as literals in Terraform, credentials kept in state,
  credential variables not marked sensitive, a .env copied into an image
* ACR04x no log delivery, no TRACES delivery, no Transaction Search, a Lambda
  behind the MCP route or a gateway target without active tracing, a Node.js
  function with no ADOT layer or tracer, an HTTP API that cannot be traced
* ACR05x a gateway target with no outbound credential, a Lambda target with
  anything but the gateway role, plain-http upstreams, DYNAMIC listing with
  semantic search
* ACR06x a Runtime image that is not ARM64, no /ping for an HTTP runtime, a
  Python MCP server that is not stateless
* ACR07x MCP supported_versions unpinned or unsupported
* ACR08x memory expiry outside 7..365 days, no customer-managed key,
  too many strategies
* ACR09x an old hashicorp/aws lock, the deprecated starter toolkit

Scope: pointed at a directory, the review reads every `.tf` below it *and*
the local modules those files call from outside it, so
`review.py infrastructure/live/hackathon` sees what that environment deploys
through `source = "../../modules/<x>"`. For a monorepo with several
environments, keep the repository as the project (so application code is
still scanned for tracers and MCP servers) and pick the environment with
`--env infrastructure/live/<env>` (`--root` is an alias): findings then come
from that environment and its modules only, never from a sibling environment.

    review.py <project> [--env infrastructure/live/<env>] [--region eu-central-1]
              [--fail-on error|warn] [--json]

Report only; nothing is written. Exit codes: 0 no blocking findings, 1
findings at or above --fail-on (default error), 2 the target does not exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import cli, rules  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, GapReport, Option  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--env", "--root", dest="env", help="review only this Terraform/Terragrunt environment "
                        "directory (relative to the project) and the local modules it calls")
    parser.add_argument("--region", help="check availability against this region instead of the resolved one")
    parser.add_argument("--fail-on", choices=("error", "warn"), default="error")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    target = Path(args.project).expanduser()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return EXIT_USAGE
    if args.env:
        env_dir = Path(args.env).expanduser()
        env_dir = env_dir if env_dir.is_absolute() else target / env_dir
        if not env_dir.is_dir():
            print(f"error: --env {args.env}: {env_dir} is not a directory", file=sys.stderr)
            return EXIT_USAGE
    project = load(target, env=args.env)
    report = GapReport(subject=str(project.root), skill="agentcore-review")
    rules.run_all(project, report, region_override=args.region)
    report.discovered = {
        "region": args.region or project.primary_region() or "not resolved",
        "agentcore_resources": len(project.agentcore_resources()),
        "terraform_files": len(project.tf.files),
        "environment": args.env or "everything under the project",
        "modules_followed": [project.rel(d) for d in project.tf.module_dirs],
        "rules_checked_against": rules.DOCS_CHECKED,
    }
    areas = sorted({f.area for f in report.findings})
    if report.findings:
        report.add_option(Option(key="1", label="Fix the errors first", recommended=bool(report.count("error")),
                                 detail="each finding names its file, line and fix", cost="free"))
    if "observability" in areas:
        report.add_option(Option(key=str(len(report.options) + 1), label="Generate the tracing changes",
                                 detail="/agentcore:agentcore-observe writes the log delivery module and the Lambda "
                                        "tracing patch", cost="free", recommended=not report.count("error")))
    if "inbound-auth" in areas or "targets" in areas:
        report.add_option(Option(key=str(len(report.options) + 1), label="Re-plan the gateway",
                                 detail="/agentcore:agentcore-gateway regenerates the gateway with a Cognito JWT "
                                        "authorizer and an outbound credential", cost="free"))
    print(report.render(args.format))
    if report.count("error") or (args.fail_on == "warn" and report.count("warn")):
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
