#!/usr/bin/env python3
"""Verify a deployed AgentCore Gateway (and optionally a Runtime container) from outside.

Post-deploy, the questions are concrete: does the gateway accept a real token,
does tools/list return the tools you expect (with the target prefix), does one
tool call succeed, how long does it take at p50 and p95 against your budget,
and does it behave in each MCP revision you pinned. This script asks exactly
those, over HTTPS with the standard library, and nothing else:

* 2025-* revisions: initialize -> Mcp-Session-Id -> notifications/initialized
  -> tools/list -> tools/call;
* 2026-07-28: no handshake; MCP-Protocol-Version and Mcp-Method headers and
  params._meta on every request;
* --protocol both runs each and compares the tool lists;
* --samples N repeats the call (or tools/list) N times for p50/p95;
* --ping-url checks a Runtime container's GET /ping (a local `docker run` of
  the image; the deployed Runtime is reached through InvokeAgentRuntime with
  SigV4, which scripts/aws_checks.py emits as an aws CLI command).

The bearer token is read from the environment variable named by --token-env,
never from the command line, and is redacted from all output. --dry-run prints
the requests that would be sent and sends nothing.

    verify.py --gateway-url URL [--token-env GATEWAY_TOKEN] [--protocol 2025-11-25|2026-07-28|both]
              [--call TOOL --args '{"k": "v"}'] [--expect-tool NAME ...] [--samples 20]
              [--budget-ms 500] [--ping-url http://localhost:8080/ping] [--timeout 15]
              [--dry-run] [--json]

Findings are the VER0xx band. Exit codes: 0 all checks passed, 1 a check
failed, 2 bad arguments, 3 the endpoint could not be reached at all.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DEFAULT_BUDGET_MS, GATEWAY_TOOL_SEPARATOR, cli, data  # noqa: E402
from agentcore_skills.mcp_http import Client, McpError, ping, redact  # noqa: E402
from agentcore_skills.report import EXIT_FINDINGS, EXIT_INCONCLUSIVE, EXIT_OK, EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.stats import summarize  # noqa: E402

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"


def probe(url: str, protocol: str, token: str | None, args, report: GapReport) -> dict:
    client = Client(url, protocol=protocol, token=token, timeout=args.timeout)
    result: dict = {"protocol": protocol}
    try:
        init = client.initialize()
        if init is not None:
            result["initialize_ms"] = round(init.elapsed_ms, 2)
            result["session_id_issued"] = bool(client.session_id)
            result["negotiated"] = client.negotiated
            if client.negotiated and client.negotiated != protocol:
                report.add("VER007", "warn", "protocol",
                           f"asked for {protocol}, the gateway negotiated {client.negotiated}",
                           fix="add the revision to protocol_configuration.mcp.supported_versions if you need it.",
                           source=f"{DOCS}/gateway-using.html")
        tools, exchange = client.list_tools()
        result["tools_list_ms"] = round(exchange.elapsed_ms, 2)
        result["tools"] = [t.get("name") for t in tools]
        if not tools:
            report.add("VER003", "error", "tools", f"tools/list returned no tools ({protocol})",
                       fix="check the target status and run SynchronizeGatewayTargets for DEFAULT listing.",
                       source=f"{DOCS}/gateway-target-MCPservers.html")
        for expected in args.expect_tool or []:
            if not any(name == expected or str(name).endswith(GATEWAY_TOOL_SEPARATOR + expected) for name in result["tools"]):
                report.add("VER008", "error", "tools", f"expected tool {expected!r} is not listed ({protocol})",
                           fix=f"gateway names are <target>{GATEWAY_TOOL_SEPARATOR}<tool>.")
        timings: list[float] = []
        if args.call:
            call_args = json.loads(args.args or "{}")
            name = args.call
            if GATEWAY_TOOL_SEPARATOR not in name:
                match = [t for t in result["tools"] if str(t).endswith(GATEWAY_TOOL_SEPARATOR + name)]
                name = match[0] if match else name
            for _ in range(max(1, args.samples)):
                exchange = client.call_tool(name, call_args)
                timings.append(exchange.elapsed_ms)
                body = (exchange.response or {}).get("result") or {}
                if body.get("isError"):
                    text = " ".join(c.get("text", "") for c in body.get("content", []) if isinstance(c, dict))[:200]
                    report.add("VER004", "error", "call", f"{name} returned isError ({protocol}): {text}",
                               fix="read the upstream's logs for this request id; the gateway reached it.")
                    break
            result["called"] = name
        elif args.samples > 1:
            for _ in range(args.samples):
                _, exchange = client.list_tools()
                timings.append(exchange.elapsed_ms)
        if timings:
            result["latency"] = summarize(timings, budget_ms=args.budget_ms)
            if result["latency"]["p95_ms"] > args.budget_ms:
                report.add("VER005", "warn", "latency",
                           f"p95 {result['latency']['p95_ms']} ms over {len(timings)} sample(s) exceeds the "
                           f"{args.budget_ms} ms budget ({protocol})",
                           fix="export traces for these calls and run agentcore-observe's trace_report.py to see "
                               "which segment owns the time.")
    except McpError as exc:
        result["error"] = str(exc)
        if exc.status in (401, 403):
            hint = {k: v for k, v in exc.headers.items() if k.lower() == "www-authenticate"}
            report.add("VER002", "error", "auth", f"HTTP {exc.status} from the gateway ({protocol}): the token was refused",
                       fix="check the token's issuer matches discovery_url, its client_id is in allowed_clients, and "
                           f"it carries any allowed_scopes. {json.dumps(hint) if hint else ''}".strip(),
                       source=f"{DOCS}/gateway-inbound-auth.html")
        elif exc.status is None and "could not reach" in str(exc):
            result["unreachable"] = True
            report.add("VER001", "error", "reachability", str(exc), fix="check the URL (it ends in /mcp) and DNS.")
        else:
            report.add("VER006", "error", "protocol", f"{exc} ({protocol})", fix=exc.body[:200] if exc.body else None)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("--gateway-url", help="https://<id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp")
    parser.add_argument("--token-env", default="GATEWAY_TOKEN", help="environment variable holding the bearer token")
    parser.add_argument("--protocol", default="2025-11-25",
                        choices=("2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28", "both"))
    parser.add_argument("--call", help="tool to call (with or without the <target>___ prefix)")
    parser.add_argument("--args", default="{}", help="JSON arguments for --call")
    parser.add_argument("--expect-tool", action="append", help="a tool that must be listed (repeatable)")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--budget-ms", type=float, default=float(DEFAULT_BUDGET_MS))
    parser.add_argument("--ping-url", help="a Runtime container's /ping, e.g. http://localhost:8080/ping")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true", help="print the requests; send nothing")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    if not args.gateway_url and not args.ping_url:
        print("error: pass --gateway-url and/or --ping-url", file=sys.stderr)
        return EXIT_USAGE
    try:
        json.loads(args.args or "{}")
    except ValueError as exc:
        print(f"error: --args is not JSON: {exc}", file=sys.stderr)
        return EXIT_USAGE
    token = os.environ.get(args.token_env) if args.token_env else None
    protocols = ["2025-11-25", "2026-07-28"] if args.protocol == "both" else [args.protocol]
    report = GapReport(subject=args.gateway_url or args.ping_url, skill="agentcore-verify")

    if args.dry_run:
        planned = []
        for protocol in protocols:
            client = Client(args.gateway_url or "", protocol=protocol, token=token or "<from $" + args.token_env + ">")
            steps = ([] if client.stateless else ["initialize", "notifications/initialized"]) + ["tools/list"]
            if args.call:
                steps += ["tools/call"] * max(1, args.samples)
            for step in steps:
                planned.append({"protocol": protocol, "method": step, "url": args.gateway_url,
                                "headers": redact(client.headers_for(step)),
                                "body": client.payload_for(step, {"name": args.call} if step == "tools/call" else None,
                                                           notify=step.startswith("notifications/"))})
        if args.ping_url:
            planned.append({"method": "GET", "url": args.ping_url})
        payload = {"dry_run": True, "requests": planned, "token_present": bool(token),
                   "note": "nothing was sent"}
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print("# agentcore-verify (dry run)\n")
            for item in planned:
                print(f"- {item.get('protocol', '')} {item['method']} {item['url']}")
            print(f"\nToken in ${args.token_env}: {'yes' if token else 'NO - export it before the real run'}")
            print("\n_Dry run: nothing was sent._")
        return EXIT_OK

    results = []
    if args.gateway_url:
        if not token:
            report.add("VER010", "warn", "auth", f"${args.token_env} is empty; calling without a bearer token",
                       fix="a CUSTOM_JWT gateway will answer 401; that proves the authorizer is on, nothing more.")
        for protocol in protocols:
            results.append(probe(args.gateway_url, protocol, token, args, report))
        if len(results) == 2 and "tools" in results[0] and "tools" in results[1] and \
                sorted(results[0]["tools"]) != sorted(results[1]["tools"]):
            report.add("VER011", "warn", "protocol", "the two revisions list different tools",
                       fix="compare the lists; a 2026-07-28-only tool feature may not translate.",
                       source=data.mcp_versions()["sources"][2])
    ping_result = None
    if args.ping_url:
        try:
            status, body, elapsed = ping(args.ping_url, timeout=args.timeout)
            ping_result = {"status_code": status, "body": body, "elapsed_ms": round(elapsed, 2)}
            if status != 200 or not body or body.get("status") not in ("Healthy", "HealthyBusy"):
                report.add("VER009", "error", "runtime", f"/ping answered {status} {body}",
                           fix="return 200 with {\"status\": \"Healthy\"} or \"HealthyBusy\".",
                           source=f"{DOCS}/runtime-http-protocol-contract.html")
        except McpError as exc:
            ping_result = {"error": str(exc)}
            report.add("VER001", "error", "reachability", str(exc))
    report.discovered = {"gateway": results, "ping": ping_result, "budget_ms": args.budget_ms,
                         "measured_from": "this machine: includes client network round trips; X-Ray shows server-side time"}
    print(report.render(args.format))
    if results and all(r.get("unreachable") for r in results) and not ping_result:
        return EXIT_INCONCLUSIVE
    return EXIT_FINDINGS if report.has_errors() else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
