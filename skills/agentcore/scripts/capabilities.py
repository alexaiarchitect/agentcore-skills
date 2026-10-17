#!/usr/bin/env python3
"""List what the agentcore plugin can do, and route a request to one skill.

The router's job is to send a request to exactly one focused skill after
discovery has run. This script makes the routing table deterministic: it
reads every sibling skill's SKILL.md frontmatter (so the table can never
drift from the skills that exist), attaches each skill's cost tier — `free`
(reads, generates or parses files; no AWS API call) or `aws` (the step calls
AWS APIs through commands you run, and may create billable resources) — and,
given --intent, scores the request against each skill's trigger phrases.

    capabilities.py [--intent "put a gateway in front of my lambda"] [--json]

It never chooses for the user: with an intent it returns a ranked shortlist
and marks one as the suggestion. Exit codes: 0 always, 2 if the skills
directory cannot be read.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import cli, frontmatter  # noqa: E402
from agentcore_skills.report import EXIT_OK, EXIT_USAGE  # noqa: E402

SKILLS_DIR = Path(__file__).resolve().parents[2]

#: skill -> (cost tier, trigger words that route to it)
ROUTES = {
    "agentcore-discover": ("free", ["inventory", "what do i have", "discover", "scan", "which framework", "what is in"]),
    "agentcore-create": ("free", ["scaffold", "create", "new runtime", "new memory", "terraform module", "starter", "cdk"]),
    "agentcore-review": ("free", ["review", "audit", "check my", "lint", "misconfig", "security", "iam", "least privilege"]),
    "agentcore-gateway": ("free", ["gateway", "in front of", "front my", "mcp target", "lambda target", "tool search",
                                   "semantic search", "tool names", "openapi target"]),
    "agentcore-identity": ("free", ["identity", "cognito", "oauth", "jwt", "token", "credential provider", "api key",
                                    "workload identity", "token vault", "inbound", "outbound", "3lo", "m2m"]),
    "agentcore-runtime": ("free", ["runtime", "host my agent", "container", "dockerfile", "/ping", "invocations",
                                   "cold start", "session", "microvm", "arm64"]),
    "agentcore-memory": ("free", ["memory", "remember", "long-term", "short-term", "strategy", "retention", "pii"]),
    "agentcore-deploy": ("aws", ["deploy", "apply", "rollout", "rollback", "quota", "sequence", "terraform apply", "ship"]),
    "agentcore-verify": ("aws", ["verify", "smoke test", "is it working", "tools/list", "probe", "health", "latency test",
                                 "p95", "post-deploy"]),
    "agentcore-observe": ("free", ["x-ray", "xray", "trace", "tracing", "otel", "opentelemetry", "adot", "where did the time",
                                   "latency", "slow", "observability", "cloudwatch", "spans"]),
    "agentcore-cost": ("free", ["cost", "price", "pricing", "bill", "budget", "how much", "estimate", "free tier"]),
    "agentcore-ci": ("free", ["ci", "pipeline", "github actions", "plan-only", "policy check", "gate", "pull request"]),
}


def load_skills() -> list[dict]:
    out = []
    for path in sorted(SKILLS_DIR.iterdir()):
        skill = path / "SKILL.md"
        if not skill.is_file():
            continue
        meta = frontmatter.read(str(skill)).meta
        name = meta.get("name", path.name)
        cost, words = ROUTES.get(name, ("free", []))
        description = str(meta.get("description", ""))
        out.append({"skill": name, "command": f"/agentcore:{name}", "cost": cost,
                    "summary": re.split(r"(?<=\.)\s", description, maxsplit=1)[0], "triggers": words})
    return out


def score(intent: str, skill: dict) -> int:
    text = f" {intent.lower()} "
    return sum(3 if " " in word else 2 for word in skill["triggers"] if word in text)


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("--intent", help="the user's request, in their words")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    try:
        skills = load_skills()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    ranked = []
    if args.intent:
        ranked = sorted(((score(args.intent, s), s["skill"]) for s in skills if s["skill"] != "agentcore"),
                        key=lambda pair: (-pair[0], pair[1]))
        ranked = [{"skill": name, "score": points} for points, name in ranked if points > 0][:3]
    suggestion = ranked[0]["skill"] if ranked else "agentcore-discover"
    if args.format == "json":
        import json
        print(json.dumps({"skills": skills, "intent": args.intent, "ranked": ranked,
                          "suggestion": suggestion,
                          "cost_tiers": {"free": "reads, generates or parses files; no AWS API call",
                                         "aws": "calls AWS APIs through commands you run; may create billable resources"}},
                         indent=2))
        return EXIT_OK
    print("# agentcore skills\n")
    print("| Skill | Cost | What it does |\n|---|---|---|")
    for s in skills:
        print(f"| `{s['command']}` | {s['cost']} | {s['summary']} |")
    if args.intent:
        print(f"\n## For: {args.intent!r}\n")
        for row in ranked:
            print(f"- `/agentcore:{row['skill']}` (score {row['score']})")
        print(f"\nSuggestion: `/agentcore:{suggestion}` — run discovery first if it has not run.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
