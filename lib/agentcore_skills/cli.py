"""Argument and output conventions every script in the plugin shares.

Generators print a write plan and touch the disk only without `--dry-run`;
checkers print a gap report. Both speak markdown by default and JSON with
`--json`, and both use the exit codes in `report.py`. Keeping that here means
a skill can drive any script the same way, and the tests can hold all of
them to it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .report import EXIT_FINDINGS, EXIT_OK, GapReport
from .templating import WritePlan


def parser(doc: str | None) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)


def add_format(p: argparse.ArgumentParser) -> None:
    p.add_argument("--format", choices=("json", "md"), default="md")
    p.add_argument("--json", action="store_const", const="json", dest="format",
                   help="print JSON instead of markdown")


def add_writer(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true", help="print the write plan; write nothing")
    p.add_argument("--force", action="store_true", help="replace files that already exist")
    add_format(p)


def finish_plan(plan: WritePlan, *, fmt: str, dry_run: bool, report: GapReport | None = None,
                extra: dict[str, Any] | None = None, notes: list[str] | None = None) -> int:
    written: list[str] = []
    if not dry_run:
        written = plan.apply()
    if fmt == "json":
        payload: dict[str, Any] = {"dry_run": dry_run, "plan": plan.to_dict(), "written": written}
        if report is not None:
            payload["report"] = report.to_dict()
        if extra:
            payload.update(extra)
        print(json.dumps(payload, indent=2))
    else:
        parts = []
        if report is not None and (report.findings or report.discovered):
            parts.append(report.to_md())
        parts.append(plan.to_md())
        if notes:
            parts.append("## Next\n\n" + "\n".join(f"- {n}" for n in notes))
        parts.append("_Dry run: nothing was written._" if dry_run else
                     f"_Wrote {len(written)} file(s)._")
        print("\n\n".join(parts))
    if report is not None and report.has_errors():
        return EXIT_FINDINGS
    if not plan.writable and not plan.items:
        return EXIT_FINDINGS
    return EXIT_OK


def modules_root(project: Path, out_dir: str | None) -> Path:
    """The directory modules are written *into*: `--out-dir`, else infrastructure/modules or terraform/modules."""
    if out_dir:
        path = Path(out_dir)
        return path if path.is_absolute() else project / path
    infra = project / "infrastructure" / "modules"
    if infra.is_dir():
        return infra
    return project / "terraform" / "modules"


def module_dir(project: Path, out_dir: str | None, default: str) -> Path:
    if out_dir:
        path = Path(out_dir)
        return path if path.is_absolute() else project / path
    infra = project / "infrastructure" / "modules"
    if infra.is_dir():
        return infra / default
    return project / "terraform" / "modules" / default
