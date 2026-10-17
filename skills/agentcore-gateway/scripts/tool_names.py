#!/usr/bin/env python3
"""Check that a server's tool names survive being put behind an AgentCore Gateway.

A gateway exposes every tool as "<target_name>___<tool_name>" (three
underscores), so a name that was fine on the server can break behind the
gateway: the prefixed name has a 256-character quota, two targets can collide,
and clients that validate names against the MCP guidance (1-128 characters
from A-Z a-z 0-9 _ - .) may reject what the gateway lists. A Lambda target
also has to strip the prefix itself.

Tool names are read from one of:
  * a JSON file: a tools/list result ({"tools": [...]}), a list of tool
    objects, a list of names, or the mcp-server plugin's `probe.py --json`
    report (`discovered.tool_names`) — what a live server actually lists;
  * --from-code DIR: TypeScript registerTool("name", ...) / server.tool("name"
    ...) calls and Python @mcp.tool / @server.tool decorators.

With both, the JSON (probed) list decides which tools count and the code only
supplies where each is registered, so tools another deployment profile
registers are not counted. --target-type says what the target is: the
Lambda-only note (GWY014, strip the prefix from bedrockAgentCoreToolName) is
given for `lambda`, and not for an `mcp` or `openapi` target, where the
gateway itself maps the prefixed name back.

    tool_names.py [tools.json] [--from-code DIR] --target-name NAME
                  [--target-type mcp|lambda|openapi] [--json]

Findings are the GWY01x band. Exit codes: 0 no errors, 1 errors, 2 no input.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import GATEWAY_TOOL_SEPARATOR, cli, data, hcl  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport, exit_code_for  # noqa: E402

TS_TOOL = re.compile(r"""(?:registerTool|\.tool)\(\s*["'`]([^"'`]+)["'`]""")
MCP_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")
DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"


def names_from_json(path: Path) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, dict):
        doc = ((doc.get("discovered") or {}).get("tool_names") or doc.get("tools")
               or (doc.get("result") or {}).get("tools") or [])
    out = []
    for item in doc:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and "name" in item:
            out.append(str(item["name"]))
    return out


def names_from_code(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in hcl.iter_files(root, (".ts", ".js", ".mjs", ".py")):
        text = hcl.read_text(path)
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for deco in node.decorator_list:
                        fn = deco.func if isinstance(deco, ast.Call) else deco
                        if isinstance(fn, ast.Attribute) and fn.attr == "tool":
                            name = node.name
                            if isinstance(deco, ast.Call):
                                for kw in deco.keywords:
                                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                                        name = str(kw.value.value)
                            found.append((name, f"{path.name}:{node.lineno}"))
        else:
            for match in TS_TOOL.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                found.append((match.group(1), f"{path.name}:{line}"))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("tools", nargs="?", help="JSON file with tool names")
    parser.add_argument("--from-code", help="scan server source for tool registrations")
    parser.add_argument("--target-name", required=True, help="the gateway target name (the prefix)")
    parser.add_argument("--target-type", choices=("mcp", "lambda", "openapi"),
                        help="the target kind; GWY014 (strip the prefix in the handler) applies to lambda only")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    entries: list[tuple[str, str]] = []
    try:
        listed = names_from_json(Path(args.tools)) if args.tools else []
        listed = [n.split(GATEWAY_TOOL_SEPARATOR, 1)[-1] for n in listed]
        coded = names_from_code(Path(args.from_code)) if args.from_code else []
        if listed:
            where = {}
            for name, loc in coded:
                where.setdefault(name, loc)
            entries = [(n, where.get(n, Path(args.tools).name)) for n in listed]
        else:
            entries = coded
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not entries:
        print("error: no tool names found (pass a JSON file or --from-code DIR)", file=sys.stderr)
        return EXIT_USAGE
    limit = data.quota("gateway.tool_name_chars")
    report = GapReport(subject=args.target_name, skill="agentcore-gateway")
    if GATEWAY_TOOL_SEPARATOR in args.target_name:
        report.add("GWY013", "warn", "names", f"the target name contains '{GATEWAY_TOOL_SEPARATOR}', which is the "
                   "gateway's own separator", fix="a handler that splits on it will cut in the wrong place.",
                   source=f"{DOCS}/gateway-add-target-lambda.html")
    seen: dict[str, str] = {}
    rows = []
    for name, where in entries:
        full = f"{args.target_name}{GATEWAY_TOOL_SEPARATOR}{name}"
        rows.append({"tool": name, "gateway_name": full, "length": len(full), "where": where})
        if len(full) > limit:
            report.add("GWY010", "error", "names", f"{full} is {len(full)} characters; the gateway quota is {limit}",
                       locator=where, fix="shorten the target name or the tool name.",
                       source=data.quotas()["source"])
        if not MCP_NAME.match(full):
            report.add("GWY011", "warn", "names",
                       f"{full} falls outside 1-128 characters of A-Z a-z 0-9 _ - . (MCP tool-name guidance)",
                       locator=where, fix="strict clients may refuse it; shorten the prefix.",
                       source="https://modelcontextprotocol.io/specification/2025-11-25/server/tools")
        if full in seen:
            report.add("GWY012", "error", "names", f"{full} is registered twice ({seen[full]} and {where})",
                       locator=where, fix="tool names must be unique per target.")
        seen[full] = where
    report.discovered = {"target_name": args.target_name, "target_type": args.target_type or "not given",
                         "tools": len(rows), "counted_from": "probed/listed tools" if args.tools else "source code",
                         "longest": max(r["length"] for r in rows),
                         "quota": limit, "names": [r["gateway_name"] for r in rows]}
    if args.target_type in (None, "lambda"):
        report.add("GWY014", "info", "names", ("a Lambda target" if args.target_type else
                   "if this is a Lambda target (pass --target-type), it") + " receives the prefixed name in "
                   "context.client_context.custom.bedrockAgentCoreToolName; strip the prefix before dispatch",
                   source=f"{DOCS}/gateway-add-target-lambda.html")
    print(report.render(args.format))
    return exit_code_for(report)


if __name__ == "__main__":
    raise SystemExit(main())
