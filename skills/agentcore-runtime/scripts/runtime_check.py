#!/usr/bin/env python3
"""Check an agent or MCP server against the AgentCore Runtime container contract.

Runtime runs one microVM per session from your ARM64 image and talks to it on
a fixed contract, so a container that works on a laptop can still fail its
first invocation. The contract, per protocol:

* HTTP (and AG-UI): listen on 0.0.0.0:8080; POST /invocations (JSON in, JSON
  or SSE out); GET /ping returning {"status": "Healthy"} or "HealthyBusy".
* MCP: listen on 0.0.0.0:8000; POST /mcp with Streamable HTTP, stateless
  (the platform adds its own Mcp-Session-Id, which the server must accept).
* A2A: 0.0.0.0:9000 at /.

This reads the Dockerfile(s) and the code — never builds or runs them — and
reports the RTM0xx band: ARM64, ports, routes, host binding, statelessness, a
copied .env, root user, and whether ADOT instrumentation is in place for
AgentCore observability.

    runtime_check.py <project> [--protocol HTTP|MCP|A2A|AGUI] [--json]

Exit codes: 0 no errors, 1 errors, 2 nothing to check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import cli, hcl  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport, Option, exit_code_for  # noqa: E402

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"
PORTS = {"HTTP": "8080", "AGUI": "8080", "MCP": "8000", "A2A": "9000"}
LOOPBACK = re.compile(r"""host\s*=\s*["'](127\.0\.0\.1|localhost)["']|listen\(\s*\d+\s*,\s*["'](127\.0\.0\.1|localhost)["']""")


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--protocol", choices=tuple(PORTS), default=None)
    cli.add_format(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.exists():
        print(f"error: {root} does not exist", file=sys.stderr)
        return EXIT_USAGE
    project = load(root)
    code = project.code
    if not code.dockerfiles and not code.entrypoints and not code.mcp_servers and not project.runtimes():
        print("error: no Dockerfile, agent entrypoint, MCP server or Runtime resource found", file=sys.stderr)
        return EXIT_USAGE
    protocol = args.protocol
    if protocol is None:
        declared = [((r.find("protocol_configuration").literal("server_protocol") if r.find("protocol_configuration") else None) or "HTTP")
                    for r in project.runtimes()]
        protocol = declared[0].upper() if declared else ("MCP" if code.mcp_servers and not code.entrypoints else "HTTP")
    port = PORTS[protocol]
    report = GapReport(subject=str(project.root), skill="agentcore-runtime")
    contract = f"{DOCS}/runtime-{'mcp' if protocol == 'MCP' else 'http'}-protocol-contract.html"

    if not code.dockerfiles:
        report.add_gap("GAP-DOCKERFILE", "No Dockerfile", "Runtime needs an ARM64 container image (or a direct code "
                       "deployment zip)", "scripts/gen_dockerfile.py writes one for this protocol")
    for docker in code.dockerfiles:
        if not docker["arm64"]:
            report.add("RTM001", "error", "image", f"{docker['file']} does not target linux/arm64",
                       path=docker["file"], fix="FROM --platform=linux/arm64 <base>, or build with "
                       "`docker buildx build --platform linux/arm64`.", source=contract)
        if docker["expose"] and port not in docker["expose"]:
            report.add("RTM002", "warn", "image", f"{docker['file']} exposes {', '.join(docker['expose'])}, not {port}",
                       path=docker["file"], fix=f"the {protocol} contract listens on 0.0.0.0:{port}.",
                       source=f"{DOCS}/runtime-service-contract.html")
        if docker["copies_env"]:
            report.add("RTM007", "error", "image", f"{docker['file']} copies a .env file into the image",
                       path=docker["file"], fix="remove it and rotate anything it held; the layer keeps it.",
                       source=contract)
        if not docker["user"]:
            report.add("RTM008", "info", "image", f"{docker['file']} runs as root", path=docker["file"],
                       fix="add a non-root USER; the microVM isolates sessions, not your process from itself.")
        if not docker["otel"] and "adot" not in code.tracing:
            report.add("RTM009", "info", "observability",
                       f"{docker['file']} does not start under opentelemetry-instrument and no ADOT dependency was found",
                       path=docker["file"], fix="add aws-opentelemetry-distro and CMD [\"opentelemetry-instrument\", ...] "
                       "so spans reach CloudWatch GenAI observability.", source=f"{DOCS}/observability-configure.html")
    if protocol in ("HTTP", "AGUI"):
        if "/ping" not in code.routes:
            report.add("RTM003", "warn", "contract", "no GET /ping handler found",
                       path=str(project.root), fix="return {\"status\": \"Healthy\"}; set time_of_last_update only "
                       "when the status changes. BedrockAgentCoreApp serves it for you.", source=contract)
        if "/invocations" not in code.routes:
            report.add("RTM004", "warn", "contract", "no POST /invocations handler found", path=str(project.root),
                       fix="BedrockAgentCoreApp's @app.entrypoint serves it.", source=contract)
    if protocol == "MCP":
        if "/mcp" not in code.routes and not any(s["kind"].startswith("python") for s in code.mcp_servers):
            report.add("RTM005", "warn", "contract", "no /mcp Streamable HTTP endpoint found", path=str(project.root),
                       fix="serve POST /mcp on 0.0.0.0:8000.", source=contract)
        py = [s for s in code.mcp_servers if s["kind"].startswith("python")]
        if py and not code.stateless_http:
            report.add("RTM006", "warn", "contract", "Python MCP server without stateless_http=True",
                       path=py[0]["file"], fix="FastMCP(host=\"0.0.0.0\", stateless_http=True); "
                       "mcp.run(transport=\"streamable-http\").", source=contract)
    for path in hcl.iter_files(project.root, (".py", ".ts", ".js")):
        if LOOPBACK.search(hcl.read_text(path)):
            report.add("RTM011", "warn", "contract", f"{project.rel(path)} binds to loopback",
                       path=project.rel(path), fix="bind 0.0.0.0 inside the container.", source=contract)
    report.add("RTM010", "info", "latency",
               "each new session provisions a microVM; reuse the session id (>= 33 characters) for every call in "
               "a conversation, or each request may pay a cold start",
               fix="measure first-call vs warm-call latency with /agentcore:agentcore-verify before committing to a budget.",
               source=f"{DOCS}/runtime-sessions.html")
    report.discovered = {"protocol": protocol, "port": port, "dockerfiles": [d["file"] for d in code.dockerfiles],
                         "routes": sorted(code.routes), "entrypoints": [e["function"] for e in code.entrypoints],
                         "frameworks": sorted(code.frameworks)}
    report.add_option(Option(key="1", label="Generate a contract-correct Dockerfile",
                             detail="scripts/gen_dockerfile.py: linux/arm64, non-root, port " + port +
                                    ", opentelemetry-instrument", cost="free", writes=["Dockerfile", ".dockerignore"],
                             recommended=bool(report.count("error"))))
    report.add_option(Option(key="2", label="Scaffold the Runtime resource in Terraform",
                             detail="/agentcore:agentcore-create --component runtime", cost="free"))
    print(report.render(args.format))
    return exit_code_for(report)


if __name__ == "__main__":
    raise SystemExit(main())
