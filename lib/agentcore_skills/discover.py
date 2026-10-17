"""The discovery pass every skill starts from: the `DSC0xx` band.

Discovery answers, with a file and line for each answer: is this project
already on AgentCore and through which door (Terraform, CDK, the AgentCore
CLI's `agentcore.json`, the starter toolkit, boto3), which agent framework
and MCP server it runs, how inbound auth works today, which region it deploys
to and whether AgentCore offers each service there, which Terraform provider
it has locked, and whether anything is traced. It then offers next steps, each
with a cost tier, and recommends exactly one.

Discovery never judges code quality — that is `agentcore-review`. Its
findings are about what could not be determined (`DSC001` nothing to work on,
`DSC002` no region) or what would make every later step misleading
(`DSC003` the starter toolkit, `DSC004` two IaC tools owning AgentCore).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import DOCS_CHECKED, GATEWAY_MCP_VERSIONS, data
from .project import Project, load, provider_version
from .report import GapReport, Option
from .rules import mcp_backend_lambdas

ALL_FOCUS = ("agentcore", "app", "auth", "region", "terraform", "tracing")
SERVICES = ("runtime", "gateway", "identity", "memory", "code_interpreter", "browser", "observability", "evaluations",
            "policy", "runtime_instances", "gateway_semantic_search", "web_search", "registry")


def availability_table(regions: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for region in regions:
        row = {}
        for service in SERVICES:
            value = data.service_available(service, region)
            row[service] = "yes" if value else ("no" if value is False else "unknown")
        out[region] = row
    return out


def discover(path: str | Path, *, focus: tuple[str, ...] = ALL_FOCUS) -> GapReport:
    project = load(path)
    report = GapReport(subject=str(project.root), skill="agentcore-discover")
    found: dict[str, Any] = {}

    agentcore_tf = project.agentcore_resources()
    doors = []
    if agentcore_tf:
        doors.append("terraform")
    if [c for c in project.code.cdk if "agentcore" in c["match"].lower() or c["match"].startswith("Cfn")]:
        doors.append("cdk")
    if project.code.agentcore_cli_projects:
        doors.append("agentcore-cli")
    if project.code.starter_toolkit_configs:
        doors.append("starter-toolkit")
    if project.code.boto3_clients or project.code.js_agentcore:
        doors.append("sdk-calls")
    if project.code.agentcore_sdk:
        doors.append("agentcore-python-sdk")

    if "agentcore" in focus:
        found["agentcore"] = {
            "doors": doors or ["none yet"],
            "terraform_resources": [f"{b.address} ({project.rel(b.file)}:{b.line})" for b in agentcore_tf],
            "agentcore_cli_projects": project.code.agentcore_cli_projects,
            "starter_toolkit_configs": project.code.starter_toolkit_configs,
            "cdk": [f"{c['file']} ({c['match']})" for c in project.code.cdk],
            "sdk_calls": [f"{c['file']}:{c['line']} {c['service']}" for c in project.code.boto3_clients] + project.code.js_agentcore,
            "python_sdk": sorted({f"{s['file']} ({s['import']})" for s in project.code.agentcore_sdk}),
            "identity_decorators": [f"{d['file']}:{d['line']} @{d['decorator']} {d.get('provider_name', '')}".strip()
                                    for d in project.code.identity_decorators],
        }
    if "app" in focus:
        mcp_lambdas = sorted(mcp_backend_lambdas(project))
        found["application"] = {
            "frameworks": {k: v for k, v in project.code.frameworks.items()} or "none detected",
            "mcp_servers": sorted({f"{m['file']} ({m['kind']})" for m in project.code.mcp_servers}),
            "mcp_routes": [f"{r['route']} -> {r['resource']} (auth {r['authorization']})" for r in project.mcp_routes()],
            "mcp_backend_lambdas": mcp_lambdas,
            "lambdas": [f"{b.address} {b.literal('runtime') or '?'} {', '.join(b.literal('architectures') or [])}".strip()
                        for b in project.lambdas()],
            "http_apis": [b.address for b in project.http_apis()],
            "rest_apis": [b.address for b in project.rest_apis()],
            "entrypoints": [f"{e['file']}:{e['line']} {e['function']}" for e in project.code.entrypoints],
            "routes": {k: v for k, v in project.code.routes.items()},
            "dockerfiles": [f"{d['file']} (arm64: {'yes' if d['arm64'] else 'no'}; expose {','.join(d['expose']) or '-'})"
                            for d in project.code.dockerfiles],
        }
    if "auth" in focus:
        found["auth"] = {
            "cognito_user_pools": [b.address for b in project.cognito_pools()],
            "cognito_clients": [f"{b.address} flows={','.join(b.literal('allowed_oauth_flows') or []) or '?'}"
                                for b in project.tf.resources_of("aws_cognito_user_pool_client")],
            "resource_servers": [b.address for b in project.tf.resources_of("aws_cognito_resource_server")],
            "api_gateway_jwt_authorizers": [b.address for b in project.jwt_authorizers()],
            "gateway_authorizers": [f"{g.address}: {g.literal('authorizer_type') or '?'}" for g in project.gateways()],
        }
    regions = project.all_regions()
    if "region" in focus:
        found["region"] = {
            "primary": project.primary_region() or "not resolved",
            "evidence": list(dict.fromkeys(f"{r['region']} <- {r['source']}" for r in project.regions))[:6],
            "availability": availability_table(regions[:3]) if regions else {},
            "regions_table_checked": data.regions()["checked"],
        }
    if "terraform" in focus:
        version = provider_version(project)
        found["terraform"] = {
            "files": len(project.tf.files),
            "required_version": project.tf.required_version(),
            "aws_provider_constraint": version["constraint"],
            "aws_provider_locked": version["locked"],
            "awscc_in_use": any(b.type.startswith("awscc_") for b in project.tf.blocks if b.kind == "resource"),
            "terragrunt": [project.rel(p) for p in project.root.rglob("terragrunt.hcl")
                           if ".terragrunt-cache" not in p.parts] if project.root.is_dir() else [],
        }
    if "tracing" in focus:
        found["tracing"] = {
            "lambda_tracing": [f"{b.address}: {((b.find('tracing_config').literal('mode') if b.find('tracing_config') else None) or 'PassThrough')}"
                               for b in project.lambdas()],
            "code_instrumentation": {k: v for k, v in project.code.tracing.items()} or "none detected",
            "log_delivery_sources": [b.address for b in project.tf.resources_of("aws_cloudwatch_log_delivery_source")],
            "http_api_note": "HTTP APIs cannot be X-Ray traced" if project.http_apis() else "",
        }
    found["checked"] = {"agentcore_docs": DOCS_CHECKED, "gateway_mcp_revisions": list(GATEWAY_MCP_VERSIONS)}
    report.discovered = found

    # -- findings ------------------------------------------------------------
    has_anything = project.tf.files or project.code.dockerfiles or project.code.frameworks or \
        project.code.mcp_servers or project.code.package_json or project.code.requirements
    if not has_anything:
        report.add("DSC001", "error", "discovery", "nothing to work on: no Terraform, code, container or manifest found",
                   path=str(project.root), fix="point the script at the project root.")
    if has_anything and not project.primary_region():
        report.add("DSC002", "warn", "region", "no AWS region could be resolved",
                   path=str(project.root),
                   fix="every availability and pricing answer depends on it; pass --region to later scripts.")
    if project.code.starter_toolkit_configs:
        report.add("DSC003", "warn", "tooling",
                   f"starter-toolkit config found ({', '.join(project.code.starter_toolkit_configs)}); its CLI is no longer supported",
                   path=project.code.starter_toolkit_configs[0],
                   fix="new work goes through Terraform here or the AgentCore CLI (@aws/agentcore).",
                   source="https://pypi.org/project/bedrock-agentcore-starter-toolkit/")
    owners = [d for d in doors if d in ("terraform", "cdk", "agentcore-cli", "starter-toolkit")]
    if len(owners) > 1:
        report.add("DSC004", "warn", "tooling",
                   f"AgentCore resources are declared by more than one tool: {', '.join(owners)}",
                   path=str(project.root),
                   fix="pick one owner per resource; two tools reconciling the same gateway fight on every apply.")
    region = project.primary_region()
    if region:
        for service in ("runtime", "gateway", "identity", "memory", "observability"):
            if data.service_available(service, region) is False:
                report.add("DSC005", "warn", "region", f"{service} is not offered in {region}", path=str(project.root),
                           source=data.regions()["source"])

    # -- gaps and options ------------------------------------------------------
    if not agentcore_tf and (project.mcp_routes() or project.code.mcp_servers):
        report.add_gap("GAP-GATEWAY", "No AgentCore Gateway in front of the MCP server",
                       "the server is reached directly; there is no managed inbound auth, tool catalog or "
                       "per-target outbound credentials",
                       "`/agentcore:agentcore-gateway` plans a gateway with a JWT authorizer and an MCP-server "
                       "or Lambda target, as Terraform.")
    untraced = [b for b in project.lambdas() if ((b.find("tracing_config").literal("mode") if b.find("tracing_config") else None) or "PassThrough") != "Active"]
    if untraced:
        report.add_gap("GAP-TRACING", "Lambda functions without active tracing",
                       f"{len(untraced)} function(s) never start their own X-Ray segment, so no trace shows where a "
                       "request's time goes",
                       "`/agentcore:agentcore-observe` patches tracing_config, adds the ADOT layer and summarises traces.")

    options: list[Option] = []
    if project.mcp_routes() or project.code.mcp_servers:
        options.append(Option(key="", label="Put an AgentCore Gateway in front of the MCP server",
                              detail="agentcore-gateway: target choice, Cognito JWT authorizer, outbound credential, "
                                     "MCP revision pinning; writes Terraform after a dry run",
                              cost="free", writes=["infrastructure/modules/agentcore-gateway/*.tf"]))
    options.append(Option(key="", label="Review the project statically (ACR0xx)",
                          detail="agentcore-review: region, inbound JWT, IAM breadth, secrets, tracing, targets, "
                                 "container contract", cost="free"))
    if untraced or project.http_apis():
        options.append(Option(key="", label="Make the time visible end to end",
                              detail="agentcore-observe: Lambda active tracing + ADOT, Transaction Search, gateway "
                                     "spans; trace_report.py on exported traces", cost="free",
                              writes=["Terraform patch", "transaction-search.sh"]))
    options.append(Option(key="", label="Estimate the monthly AgentCore bill",
                          detail="agentcore-cost: from a usage profile, with every line's formula", cost="free"))
    if agentcore_tf:
        options.append(Option(key="", label="Plan the deploy and its rollback",
                              detail="agentcore-deploy: sequencing, quotas, emitted terraform/aws commands; nothing runs "
                                     "until you do", cost="aws", runs=["terraform plan/apply (you run them)"]))
        options.append(Option(key="", label="Verify what is deployed",
                              detail="agentcore-verify: tools/list and one call through the gateway, latency p50/p95 "
                                     "vs budget, emitted aws CLI checks", cost="aws"))
    for index, option in enumerate(options, start=1):
        option.key = str(index)
    if options:
        recommended = next((o for o in options if "Gateway in front" in o.label and not agentcore_tf), None) or \
            next((o for o in options if "Review" in o.label), options[0])
        recommended.recommended = True
    report.options = options
    return report
