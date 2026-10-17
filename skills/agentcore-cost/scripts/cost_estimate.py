#!/usr/bin/env python3
"""Estimate the monthly AgentCore bill from a usage profile, line by line.

The profile is a small JSON file describing expected usage (requests per day,
tool calls per request, Runtime sessions and their length, Memory events and
records, evaluations, and optionally model tokens with your own per-1,000
prices). See references/usage-profile.md for every field and
assets/profile.example.json for a filled-in example.

The estimate prices only what the published AgentCore rate card covers
(lib/agentcore_skills/data/pricing.json, with its source URL and checked date),
prints the formula for every line, and lists what it did not price (Lambda,
API Gateway, CloudWatch, X-Ray, DynamoDB) so the total is never mistaken for
the whole bill. Short-term Memory changes rate card on 2026-10-06 (per 1,000
events -> per GB); --as-of picks the card.

    cost_estimate.py <profile.json> [--as-of 2026-10-06] [--json]

Findings are the CST0xx band. Exit codes: 0 estimated, 2 the profile is
missing or invalid.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import cli, data  # noqa: E402
from agentcore_skills.cost import ProfileError, estimate  # noqa: E402
from agentcore_skills.report import EXIT_OK, EXIT_USAGE, GapReport  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("profile")
    parser.add_argument("--as-of", default=None, help="date that selects the rate card (default: today)")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    try:
        profile = json.loads(Path(args.profile).expanduser().read_text(encoding="utf-8"))
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        result = estimate(profile, as_of=as_of)
    except (OSError, ValueError, ProfileError) as exc:
        print(f"error: {args.profile}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    report = GapReport(subject=str(args.profile), skill="agentcore-cost")
    prices = data.pricing()
    age = data.age_days(prices["checked"], date.fromisoformat(result["as_of"]))
    if age > 90:
        report.add("CST004", "warn", "pricing", f"the rate card was checked {age} days before --as-of",
                   fix="refresh lib/agentcore_skills/data/pricing.json from the pricing page.", source=prices["source"])
    report.add("CST002", "info", "scope", "not priced here: " + ", ".join(result["unpriced"]),
               fix="add them from their own pricing pages; for a Lambda-backed gateway they are often larger "
                   "than the AgentCore lines.")
    if (profile.get("memory") or {}) and result["memory_rate_card"] == "events":
        report.add("CST003", "info", "pricing", "short-term Memory is priced per 1,000 events until 2026-10-05 and "
                   "per GB ingested from 2026-10-06; re-run with --as-of 2026-10-06 to see the new card",
                   source=prices["source"])
    report.add("CST005", "info", "pricing", prices["region_note"], source=prices["source"])
    if profile.get("region") and data.service_available("gateway", profile["region"]) is False:
        report.add("CST001", "warn", "region", f"gateway is not offered in {profile['region']}",
                   source=data.regions()["source"])
    report.discovered = {"profile": result["name"], "region": result["region"], "as_of": result["as_of"],
                         "total_monthly_usd": result["total_monthly_usd"], "by_service": result["by_service"]}
    if args.format == "json":
        payload = report.to_dict()
        payload["estimate"] = result
        print(json.dumps(payload, indent=2))
        return EXIT_OK
    print(report.to_md())
    print("\n## Lines\n\n| service | item | quantity | monthly USD | formula |\n|---|---|---:|---:|---|")
    for line in result["lines"]:
        print(f"| {line['service']} | {line['item']} | {line['quantity']:,} {line['unit']} | {line['monthly_usd']:.4f} | "
              f"{line['formula']}{' — ' + line['note'] if line.get('note') else ''} |")
    print(f"\n**Total (AgentCore lines only): ${result['total_monthly_usd']:.2f} per month** — list prices from "
          f"{result['pricing_source']} (checked {result['pricing_checked']}).")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
