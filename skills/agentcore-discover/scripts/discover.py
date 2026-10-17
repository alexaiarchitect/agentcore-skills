#!/usr/bin/env python3
"""Inventory a project for Amazon Bedrock AgentCore work and print a gap report.

Every skill in this plugin starts here, because the answers that decide what
to do next are the ones people guess wrong: is anything already on AgentCore
(and through which tool: Terraform, CDK, the AgentCore CLI's agentcore.json,
the deprecated starter toolkit, boto3), which agent framework and MCP server
the project runs, how inbound auth works today (Cognito, an API Gateway JWT
authorizer), which region it deploys to and whether AgentCore offers each
service there, which hashicorp/aws provider is locked, and whether any request
is traced. Files are read, never executed; no AWS call is made.

    discover.py <project> [--focus agentcore,app,auth,region,terraform,tracing] [--json]

Findings are the DSC0xx band. Exit codes: 0 nothing blocking, 1 errors,
2 the target does not exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import cli  # noqa: E402
from agentcore_skills.discover import ALL_FOCUS, discover  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, exit_code_for  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".", help="project root (or a single file)")
    parser.add_argument("--focus", default=",".join(ALL_FOCUS),
                        help=f"comma-separated subset of {', '.join(ALL_FOCUS)}")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    target = Path(args.project).expanduser()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return EXIT_USAGE
    focus = tuple(f.strip() for f in args.focus.split(",") if f.strip())
    unknown = sorted(set(focus) - set(ALL_FOCUS))
    if unknown:
        print(f"error: unknown focus {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    report = discover(target, focus=focus)
    print(report.render(args.format))
    return exit_code_for(report)


if __name__ == "__main__":
    raise SystemExit(main())
