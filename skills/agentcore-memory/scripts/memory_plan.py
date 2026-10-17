#!/usr/bin/env python3
"""Plan an AgentCore Memory resource: retention, strategies, encryption, PII.

AgentCore Memory keeps two things with different lifetimes. Short-term memory
is the raw events of a session (each user turn and agent reply), kept for
event_expiry_duration days (7 to 365). Long-term memory is what strategies
extract from those events — facts (SEMANTIC), session
summaries (SUMMARIZATION), user preferences (USER_PREFERENCE), episodes
(EPISODIC) — kept as records scoped by namespace. At most six strategies per
memory, one of each built-in type.

The script reads any existing aws_bedrockagentcore_memory resources and the
agent code's memory usage, checks the requested settings (MEM0xx: retention
range, strategy count and duplicates, PII without a customer-managed key,
actor-scoped namespaces), and writes a Terraform module.

    memory_plan.py <project> [--name NAME] [--expiry-days 30]
                   [--strategies SEMANTIC,SUMMARIZATION] [--kms | --no-kms] [--pii]
                   [--out-dir DIR] [--dry-run] [--force] [--json]

Exit codes: 0 planned/written, 1 an error finding (nothing is written),
2 bad arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DOCS_CHECKED, cli, data, tfgen  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_FINDINGS, EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.templating import WritePlan  # noqa: E402

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--name", default=None)
    parser.add_argument("--expiry-days", type=int, default=30)
    parser.add_argument("--strategies", default="SEMANTIC")
    kms = parser.add_mutually_exclusive_group()
    kms.add_argument("--kms", dest="kms", action="store_true", default=None, help="customer-managed KMS key")
    kms.add_argument("--no-kms", dest="kms", action="store_false")
    parser.add_argument("--pii", action="store_true", help="conversations may contain personal data")
    parser.add_argument("--out-dir", default=None)
    cli.add_writer(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    strategies = [s.strip().upper() for s in args.strategies.split(",") if s.strip()]
    project = load(root)
    report = GapReport(subject=str(project.root), skill="agentcore-memory")
    low, high = data.quota("memory.event_expiry_min_days"), data.quota("memory.event_expiry_max_days")
    if not low <= args.expiry_days <= high:
        report.add("MEM001", "error", "retention", f"--expiry-days {args.expiry_days} is outside {low}..{high}",
                   fix=f"choose {low} to {high} days.", source=data.quotas()["source"])
    unknown = [s for s in strategies if s not in tfgen.STRATEGY_TYPES]
    if unknown:
        report.add("MEM002", "error", "strategies", f"unknown or custom strategy type(s): {', '.join(unknown)}",
                   fix=f"built-in types: {', '.join(tfgen.STRATEGY_TYPES)}; CUSTOM needs a configuration block "
                       "this generator does not write.", source=f"{DOCS}/built-in-strategies.html")
    if len(set(strategies)) != len(strategies):
        report.add("MEM003", "error", "strategies", "a built-in strategy type is listed twice",
                   fix="only one strategy of each built-in type can exist per memory.",
                   source="https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory_strategy")
    if len(strategies) > data.quota("memory.strategies_per_memory"):
        report.add("MEM004", "error", "strategies", f"{len(strategies)} strategies; the limit is "
                   f"{data.quota('memory.strategies_per_memory')}", source=data.quotas()["source"])
    use_kms = args.kms if args.kms is not None else True
    if args.pii and not use_kms:
        report.add("MEM005", "warn", "pii", "personal data without a customer-managed key",
                   fix="use --kms so you control key access and can revoke it; event metadata is never "
                       "CMK-encrypted, so keep PII out of metadata in any case.", source=f"{DOCS}/memory-types.html")
    if args.pii:
        report.add("MEM006", "info", "pii",
                   f"raw events are kept {args.expiry_days} days and extracted records until deleted",
                   fix="match expiry to your retention policy, scope namespaces by {actorId}, and plan deletion "
                       "(DeleteEvent / memory-record deletion) for erasure requests.", source=f"{DOCS}/memory-types.html")
    if "USER_PREFERENCE" in strategies and not args.pii:
        report.add("MEM007", "info", "pii", "USER_PREFERENCE extracts facts about a person; that is personal data in "
                   "most jurisdictions", fix="re-run with --pii to get the retention notes.",
                   source=f"{DOCS}/built-in-strategies.html")
    existing = project.memories()
    report.discovered = {"existing_memories": [m.address for m in existing], "strategies": strategies,
                         "expiry_days": args.expiry_days, "kms": use_kms,
                         "memory_in_code": sorted({s["file"] for s in project.code.agentcore_sdk
                                                   if "memory" in s["import"]})}
    if report.has_errors():
        print(report.render(args.format))
        return EXIT_FINDINGS
    name = args.name or tfgen.aws_name(f"{root.resolve().name}-memory")
    files = tfgen.memory_module(name=name, checked=DOCS_CHECKED, expiry_days=args.expiry_days,
                                strategies=strategies, kms=use_kms)
    plan = WritePlan()
    out = cli.module_dir(root, args.out_dir, "agentcore-memory")
    for rel, content in files.items():
        plan.add(out / rel, content, force=args.force)
    notes = ["strategies run on events after they are written; do not assume a record is retrievable on the next turn - measure it",
             "pricing: see /agentcore:agentcore-cost (short-term memory moves from per-event to per-GB on 2026-10-06)"]
    return cli.finish_plan(plan, fmt=args.format, dry_run=args.dry_run, report=report, notes=notes)


if __name__ == "__main__":
    raise SystemExit(main())
