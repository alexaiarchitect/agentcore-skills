#!/usr/bin/env python3
"""Plan end-to-end tracing for an AgentCore setup and the services behind it.

A latency budget is only checkable if every hop leaves a segment. This reads
the project and reports, hop by hop, what is traced today (OBS01x):

* API Gateway: a REST API can enable X-Ray active tracing; an HTTP API
  cannot, so the Lambda segment is the first one (compare with the access
  log's $context.responseLatency for API Gateway's share);
* Lambda: tracing_config mode Active, xray:PutTraceSegments on the role, and
  for Node.js the ADOT layer (AWSOpenTelemetryDistroJs with
  AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument) or Powertools Tracer so
  DynamoDB, Secrets Manager and HTTP calls appear as subsegments;
* AgentCore Gateway, Memory, Runtime: CloudWatch log delivery with
  APPLICATION_LOGS and TRACES sources (TRACES needs Transaction Search);
* the account: Transaction Search (aws xray update-trace-segment-destination).

It writes (only without --dry-run) an observability module with the log
deliveries, transaction-search.sh, and a per-function Lambda tracing patch to
merge by hand. Every delivery source/destination and log-group name is
prefixed with the module's `name` variable (default from --name, the gateway's
literal name, or the project directory), so a second gateway or environment in
the same account and region does not collide.

    tracing_plan.py <project> [--name PREFIX] [--out-dir DIR] [--dry-run] [--force] [--json]

Exit codes: 0 planned/written, 1 nothing to write, 2 bad arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DOCS_CHECKED, cli, hcl, tfgen  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.rules import _gateway_target_lambdas, mcp_backend_lambdas  # noqa: E402
from agentcore_skills.templating import WritePlan  # noqa: E402

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--name", default=None, help="prefix for every delivery and log-group name (default: the "
                        "gateway's literal name, else the project directory); wire var.name from the caller")
    cli.add_writer(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    project = load(root)
    report = GapReport(subject=str(project.root), skill="agentcore-observe")
    region = project.primary_region() or "eu-central-1"
    hot = mcp_backend_lambdas(project) | {f"aws_lambda_function.{n}" if "." not in n else n
                                          for n in _gateway_target_lambdas(project)}
    hops = []
    for api in project.http_apis():
        hops.append({"hop": api.address, "traced": "no (HTTP API: X-Ray not supported)"})
        report.add("OBS010", "info", "api-gateway", f"{api.address} is an HTTP API and cannot emit an X-Ray segment",
                   fix="keep the access log's $context.responseLatency and $context.integrationLatency; their "
                       "difference is API Gateway's own time.",
                   source="https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html")
    for stage in project.tf.resources_of("aws_api_gateway_stage"):
        if stage.literal("xray_tracing_enabled") is not True:
            report.add("OBS011", "warn", "api-gateway", f"{stage.address} does not enable X-Ray tracing",
                       fix="xray_tracing_enabled = true", source="https://docs.aws.amazon.com/xray/latest/devguide/xray-services-apigateway.html")
    patches = []
    for fn in project.lambdas():
        tracing = fn.find("tracing_config")
        mode = (tracing.literal("mode") if tracing else None) or "PassThrough"
        layers = " ".join(hcl.strings_in(fn.get("layers")))
        adot = "OpenTelemetry" in layers or "otel" in layers.lower()
        hops.append({"hop": fn.address, "tracing_mode": mode, "adot_layer": adot, "on_request_path": fn.address in hot})
        if fn.address not in hot:
            continue
        if mode != "Active":
            report.add("OBS012", "warn", "lambda", f"{fn.address} tracing_config is {mode}",
                       path=project.rel(fn.file), locator=f"line {fn.line}", fix="mode = \"Active\"",
                       source="https://docs.aws.amazon.com/lambda/latest/dg/nodejs-tracing.html")
        if str(fn.literal("runtime") or "").startswith("nodejs") and not adot and \
                not set(project.code.tracing) & {"powertools-tracer", "aws-xray-sdk", "opentelemetry", "adot"} and \
                not (mode == "Active" and "xray-emitter" in project.code.tracing):
            report.add("OBS013", "warn", "lambda", f"{fn.address}: no ADOT layer or tracer; downstream calls are invisible",
                       path=project.rel(fn.file), locator=f"line {fn.line}",
                       fix="AWSOpenTelemetryDistroJs layer + AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument",
                       source="https://aws-otel.github.io/docs/getting-started/lambda")
        if mode != "Active" or not adot:
            patches.append(tfgen.lambda_tracing_patch(fn.address, region))
    targets = []
    wiring: list[str] = []
    for gw in project.gateways():
        tf = tfgen.tf_name(gw.name + "_gateway")
        targets.append((tf, f"var.{tf}_arn", f"gateway-{gw.name}"))
        wiring.append(f"{tf}_arn = {gw.address}.gateway_arn")
    for mem in project.memories():
        tf = tfgen.tf_name(mem.name + "_memory")
        targets.append((tf, f"var.{tf}_arn", f"memory-{mem.name}"))
        wiring.append(f"{tf}_arn = {mem.address}.arn")
    for rt in project.runtimes():
        tf = tfgen.tf_name(rt.name + "_runtime")
        targets.append((tf, f"var.{tf}_arn", f"runtime-{rt.name}"))
        wiring.append(f"{tf}_arn = {rt.address}.agent_runtime_arn")
    existing = project.tf.resources_of("aws_cloudwatch_log_delivery_source")
    if (project.gateways() or project.memories() or project.runtimes()) and not existing:
        report.add("OBS014", "warn", "agentcore", "AgentCore resources without log/trace delivery",
                   fix="the generated module adds APPLICATION_LOGS and TRACES deliveries for each.",
                   source=f"{DOCS}/observability-configure.html")
    if not targets:
        targets.append(("gateway", "var.gateway_arn", "gateway"))
        report.add("OBS015", "info", "agentcore", "no AgentCore resource in this project yet; the module takes the gateway "
                   "ARN as a variable for when it exists")
    plan = WritePlan()
    out = cli.module_dir(root, args.out_dir, "agentcore-observability")
    prefix = args.name or (project.gateways()[0].literal("name") if project.gateways() and
                            isinstance(project.gateways()[0].literal("name"), str) else root.resolve().name)
    files = tfgen.observability_module(checked=DOCS_CHECKED, targets=targets, name=prefix)
    for rel, content in files.items():
        plan.add(out / rel, content, force=args.force)
    if patches:
        plan.add(out / "lambda-tracing.patch.tf.txt", "\n".join(patches), force=args.force,
                 reason="a patch to merge by hand into the existing function blocks; not loaded by Terraform")
    report.discovered = {"region": region, "hops": hops, "request_path_lambdas": sorted(hot)}
    notes = [("wire the module with: " + "; ".join(wiring)) if wiring else "pass gateway_arn once the gateway exists",
             "run transaction-search.sh once per account and region before applying TRACES deliveries",
             "after deploying, export traces and run scripts/trace_report.py (see references/where-did-the-time-go.md)"]
    return cli.finish_plan(plan, fmt=args.format, dry_run=args.dry_run, report=report, notes=notes)


if __name__ == "__main__":
    raise SystemExit(main())
