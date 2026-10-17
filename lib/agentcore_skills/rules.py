"""The `ACR0xx` static review band: what can be wrong before anything deploys.

Every rule reads the `Project` model and adds findings to a `GapReport`.
Rules are deliberately narrow — each one names one defect, one place and one
fix — and each cites the AgentCore page it derives from. A rule that cannot
resolve a value (a region behind a module input, a policy built elsewhere)
says so with a note rather than passing silently or failing loudly.

The band, by area:

* `ACR00x` region availability (data/regions.json)
* `ACR01x` gateway inbound authorization (JWT authorizer)
* `ACR02x` IAM breadth
* `ACR03x` secrets in configuration
* `ACR04x` observability: log delivery, Transaction Search, X-Ray/ADOT
* `ACR05x` gateway targets and outbound auth
* `ACR06x` Runtime container contract (ARM64, `/ping`, stateless MCP)
* `ACR07x` gateway MCP protocol pinning
* `ACR08x` memory retention and encryption
* `ACR09x` tooling: provider versions, deprecated starter toolkit
"""

from __future__ import annotations

import re
from pathlib import Path

from . import DOCS_CHECKED, PROVIDER_MIN_ASSUMED, data, hcl, iam
from .project import Project
from .report import GapReport

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"
SRC_REGIONS = f"{DOCS}/agentcore-regions.html"
SRC_INBOUND = f"{DOCS}/gateway-inbound-auth.html"
SRC_COGNITO = f"{DOCS}/identity-getting-started-cognito.html"
SRC_OUTBOUND = f"{DOCS}/gateway-outbound-auth.html"
SRC_LAMBDA_TARGET = f"{DOCS}/gateway-add-target-lambda.html"
SRC_MCP_TARGET = f"{DOCS}/gateway-target-MCPservers.html"
SRC_OBS = f"{DOCS}/observability-configure.html"
SRC_HTTP_CONTRACT = f"{DOCS}/runtime-http-protocol-contract.html"
SRC_MCP_CONTRACT = f"{DOCS}/runtime-mcp-protocol-contract.html"
SRC_GATEWAY_USING = f"{DOCS}/gateway-using.html"
SRC_MEMORY_TF = "https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory"
SRC_MEMORY = f"{DOCS}/memory-types.html"
SRC_LAMBDA_TRACING = "https://docs.aws.amazon.com/lambda/latest/dg/nodejs-tracing.html"
SRC_HTTP_API_XRAY = "https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html"
SRC_STARTER = "https://pypi.org/project/bedrock-agentcore-starter-toolkit/"
SRC_TF_CHANGELOG = "https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md"
SRC_IAM_LEAST = "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege"

SECRET_ATTRS = ("client_secret", "api_key", "client_secret_wo", "api_key_wo", "clientSecret", "apiKey")


def _where(project: Project, block: hcl.Block) -> tuple[str, str]:
    return project.rel(block.file), f"line {block.line}"


def run_all(project: Project, report: GapReport, *, region_override: str | None = None) -> None:
    check_regions(project, report, region_override)
    check_gateway_inbound(project, report)
    check_iam(project, report)
    check_secrets(project, report)
    check_observability(project, report)
    check_targets(project, report)
    check_runtime_contract(project, report)
    check_protocol_pinning(project, report)
    check_memory(project, report)
    check_tooling(project, report)


# -- ACR00x ---------------------------------------------------------------

def check_regions(project: Project, report: GapReport, region_override: str | None) -> None:
    resources = project.agentcore_resources()
    regions = [region_override] if region_override else project.all_regions()
    primary = region_override or project.primary_region()
    if resources and not primary:
        report.add("ACR002", "warn", "region",
                   "no AWS region could be resolved for the AgentCore resources",
                   path=str(project.root),
                   fix="pin `region` on the provider (or a variable default), or pass --region so "
                       "availability can be checked against the regions table.",
                   source=SRC_REGIONS)
        return
    if not primary:
        return
    for block in resources:
        service = data.service_for_resource(block.type)
        if not service:
            continue
        available = data.service_available(service, primary)
        path, locator = _where(project, block)
        if available is False:
            report.add("ACR001", "error", "region",
                       f"{block.address} needs {service}, which is not available in {primary}",
                       path=path, locator=locator,
                       fix=f"deploy this resource in a region that offers {service} "
                           f"({', '.join(data.regions()['limited'].get(service, [])[:6])}…), or drop it.",
                       source=SRC_REGIONS)
        elif available is None:
            report.add("ACR003", "info", "region",
                       f"availability of {service} in {primary} is not in the regions table "
                       f"(checked {data.regions()['checked']})",
                       path=path, locator=locator,
                       fix="confirm on the regions page before applying.", source=SRC_REGIONS)
    for block in project.gateways():
        cfg = block.find("protocol_configuration", "mcp")
        if cfg is not None and (cfg.literal("search_type") or "").upper() == "SEMANTIC":
            if data.service_available("gateway_semantic_search", primary) is False:
                path, locator = _where(project, block)
                report.add("ACR001", "error", "region",
                           f"{block.address} enables semantic search, which is not offered in {primary}",
                           path=path, locator=locator,
                           fix="remove search_type or choose a supported region.",
                           source=f"{DOCS}/gateway-using-mcp-semantic-search.html")
    del regions


# -- ACR01x ---------------------------------------------------------------

def check_gateway_inbound(project: Project, report: GapReport) -> None:
    for block in project.gateways():
        path, locator = _where(project, block)
        kind = (block.literal("authorizer_type") or "").upper()
        raw_kind = block.get("authorizer_type")
        if raw_kind is None:
            kind = (block.literal("authorizerType") or "").upper()
        if kind == "NONE":
            report.add("ACR010", "error", "inbound-auth",
                       f"{block.address} has authorizer_type NONE: anyone who finds the URL can list and call its tools",
                       path=path, locator=locator,
                       fix="use CUSTOM_JWT with the Cognito discovery URL and allowed_clients, or AWS_IAM for "
                           "callers that sign with SigV4. NONE is meant for gateways whose authorization is "
                           "offloaded elsewhere.",
                       source=SRC_INBOUND)
            continue
        if kind == "AUTHENTICATE_ONLY":
            report.add("ACR014", "info", "inbound-auth",
                       f"{block.address} verifies the caller's SigV4 signature but makes no authorization "
                       "decision: any authenticated IAM principal can invoke it",
                       path=path, locator=locator,
                       fix="correct only when the target authorizes the IAM caller itself. AUTHENTICATE_ONLY "
                           "carries no bearer token, so it cannot be combined with token passthrough "
                           "(JWT_PASSTHROUGH needs CUSTOM_JWT or NONE inbound).",
                       source=SRC_INBOUND)
        if kind != "CUSTOM_JWT":
            continue
        jwt = block.find("authorizer_configuration", "custom_jwt_authorizer")
        if jwt is None:
            report.add("ACR011", "error", "inbound-auth",
                       f"{block.address} is CUSTOM_JWT but has no authorizer_configuration.custom_jwt_authorizer",
                       path=path, locator=locator,
                       fix="add discovery_url and at least allowed_clients (Cognito) or allowed_audience.",
                       source=SRC_INBOUND)
            continue
        url = hcl.string_or_ref(jwt.get("discovery_url"))
        if url and hcl.literal(jwt.get("discovery_url")) is not hcl.UNRESOLVED and \
                not url.rstrip("/").endswith("/.well-known/openid-configuration"):
            report.add("ACR013", "error", "inbound-auth",
                       f"{block.address} discovery_url is not an OpenID configuration URL: {url}",
                       path=path, locator=locator,
                       fix="AgentCore expects the full URL including /.well-known/openid-configuration; for "
                           "Cognito: https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration",
                       source=SRC_COGNITO)
        if not any(jwt.has(k) for k in ("allowed_clients", "allowed_audience", "allowed_scopes", "custom_claim")):
            report.add("ACR012", "warn", "inbound-auth",
                       f"{block.address} accepts any token the issuer signs: no allowed_clients, "
                       "allowed_audience, allowed_scopes or custom_claim",
                       path=path, locator=locator,
                       fix="Cognito access tokens carry client_id (and aud only when a resource binding "
                           "is used); restrict with allowed_clients, and add allowed_scopes for the tool scopes.",
                       source=SRC_INBOUND)
    for block in project.runtimes():
        if block.find("authorizer_configuration", "custom_jwt_authorizer") is None and \
                (block.find("protocol_configuration") and
                 (block.find("protocol_configuration").literal("server_protocol") or "HTTP").upper() == "MCP"):
            path, locator = _where(project, block)
            report.add("ACR015", "info", "inbound-auth",
                       f"{block.address} is an MCP runtime without a JWT authorizer; callers need SigV4",
                       path=path, locator=locator,
                       fix="fine for agent-to-runtime calls inside AWS; add custom_jwt_authorizer for OAuth clients.",
                       source=SRC_MCP_CONTRACT)


# -- ACR02x ---------------------------------------------------------------

def check_iam(project: Project, report: GapReport) -> None:
    for statement in iam.collect(project.tf):
        if statement.effect != "Allow":
            continue
        origin = statement.origin
        if iam.is_admin(statement):
            report.add("ACR020", "error", "iam",
                       f"{origin}: Allow * on * — an administrator grant",
                       path=statement.file or str(project.root), locator=statement.locator,
                       fix="grant the gateway/runtime role only the actions its targets need, on their ARNs.",
                       source=SRC_IAM_LEAST)
            continue
        wild_actions = [a for a in statement.actions if iam.is_wildcard_action(a)]
        if wild_actions and "*" in statement.resources:
            report.add("ACR021", "warn", "iam",
                       f"{origin}: {', '.join(wild_actions)} on Resource \"*\"",
                       path=statement.file or str(project.root), locator=statement.locator,
                       fix="name the actions (e.g. lambda:InvokeFunction) and scope Resource to the "
                           "target's ARN.",
                       source=SRC_IAM_LEAST)
        elif any(a.startswith("bedrock-agentcore:") for a in statement.actions) and "*" in statement.resources \
                and not statement.has_condition:
            report.add("ACR022", "info", "iam",
                       f"{origin}: bedrock-agentcore actions on Resource \"*\" without a condition",
                       path=statement.file or str(project.root), locator=statement.locator,
                       fix="scope to the gateway, runtime or workload-identity ARN where the action allows it.",
                       source=SRC_OUTBOUND)


# -- ACR03x ---------------------------------------------------------------

def check_secrets(project: Project, report: GapReport) -> None:
    for block in project.tf.blocks:
        for node in block.walk():
            for key in SECRET_ATTRS:
                raw = node.get(key)
                if raw is None:
                    continue
                value = hcl.literal(raw)
                if isinstance(value, str) and value and not value.startswith(("<", "REPLACE", "changeme")):
                    report.add("ACR030", "error", "secrets",
                               f"{block.address}: `{key}` is a literal in Terraform source",
                               path=project.rel(block.file), locator=f"line {node.line or block.line}",
                               fix="rotate it, then pass it through a sensitive variable or a write-only "
                                   "argument (`client_secret_wo`, `api_key_wo`) so it stays out of state.",
                               source="https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_oauth2_credential_provider")
                elif key in ("client_secret", "api_key") and isinstance(value, type(hcl.UNRESOLVED)) \
                        and block.type.startswith("aws_bedrockagentcore_"):
                    report.add("ACR031", "info", "secrets",
                               f"{block.address}: `{key}` is stored in Terraform state",
                               path=project.rel(block.file), locator=f"line {node.line or block.line}",
                               fix=f"prefer `{key}_wo` with a version counter; write-only arguments are not "
                                   "persisted to state.",
                               source="https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_api_key_credential_provider")
    for var in project.tf.of_kind("variable"):
        name = var.labels[0] if var.labels else ""
        if re.search(r"(secret|api_key|token|password)", name) and not re.search(r"_(arn|name|id|ids|url|version)$", name) \
                and var.literal("sensitive") is not True:
            report.add("ACR032", "warn", "secrets",
                       f"variable `{name}` looks like a credential and is not marked sensitive",
                       path=project.rel(var.file), locator=f"line {var.line}",
                       fix="add `sensitive = true` so plans and logs redact it.",
                       source="https://developer.hashicorp.com/terraform/language/values/variables#suppressing-values-in-cli-output")
    for docker in project.code.dockerfiles:
        if docker.get("copies_env"):
            report.add("ACR033", "error", "secrets",
                       f"{docker['file']} copies a .env file into the image",
                       path=docker["file"],
                       fix="delete the COPY; the file persists in the layer. Pass configuration as Runtime "
                           "environment variables and secrets through AgentCore Identity.",
                       source=SRC_HTTP_CONTRACT)


# -- ACR04x ---------------------------------------------------------------

def check_observability(project: Project, report: GapReport) -> None:
    agentcore = project.agentcore_resources()
    sources = project.tf.resources_of("aws_cloudwatch_log_delivery_source", "awscc_logs_delivery_source")
    trace_sources = [s for s in sources if (s.literal("log_type") or "").upper() == "TRACES"]
    services = {b.type for b in agentcore}
    if agentcore and not sources:
        report.add("ACR040", "warn", "observability",
                   f"{len(agentcore)} AgentCore resource(s) and no CloudWatch log delivery for any of them",
                   path=str(project.root),
                   fix="add aws_cloudwatch_log_delivery_source (APPLICATION_LOGS and TRACES) for the gateway, "
                       "memory and runtime, with destinations; `/agentcore:agentcore-observe` generates them.",
                   source=SRC_OBS)
    elif agentcore and not trace_sources and services & {"aws_bedrockagentcore_gateway", "aws_bedrockagentcore_agent_runtime"}:
        report.add("ACR041", "warn", "observability",
                   "log delivery exists but no TRACES source: gateway spans will not reach Transaction Search",
                   path=str(project.root),
                   fix="add a delivery source with log_type = \"TRACES\" and an XRAY delivery destination; "
                       "Transaction Search must be enabled first.",
                   source=SRC_OBS)
    if agentcore and not _transaction_search_evidence(project):
        report.add("ACR042", "info", "observability",
                   "no evidence that CloudWatch Transaction Search is enabled in this account",
                   path=str(project.root),
                   fix="one-time per account and region: `aws xray update-trace-segment-destination "
                       "--destination CloudWatchLogs` plus the logs resource policy for xray.amazonaws.com.",
                   source=SRC_OBS)
    gateway_lambda_refs = _gateway_target_lambdas(project)
    mcp_blocks = mcp_backend_blocks(project)
    for fn in project.lambdas():
        tracing = fn.find("tracing_config")
        mode = (tracing.literal("mode") if tracing else None) or "PassThrough"
        is_target = fn.address in gateway_lambda_refs or fn.name in gateway_lambda_refs
        serves_mcp = any(fn is block for block in mcp_blocks)
        if mode != "Active" and (is_target or serves_mcp):
            path, locator = _where(project, fn)
            report.add("ACR043", "warn", "observability",
                       f"{fn.address} tracing_config mode is {mode}: the function never starts its own segment",
                       path=path, locator=locator,
                       fix="set tracing_config { mode = \"Active\" } and grant xray:PutTraceSegments "
                           "(AWSXRayDaemonWriteAccess); without it no trace shows where the time went.",
                       source=SRC_LAMBDA_TRACING)
        runtime = fn.literal("runtime") or ""
        layers = " ".join(hcl.strings_in(fn.get("layers")) + [fn.get("layers") or ""])
        # An in-repo emitter (code reading _X_AMZN_TRACE_ID / AWS_XRAY_DAEMON_ADDRESS)
        # counts as instrumentation when the function's own segment exists (Active).
        own_emitter = mode == "Active" and "xray-emitter" in project.code.tracing
        if (is_target or serves_mcp) and str(runtime).startswith("nodejs") and "otel" not in layers.lower() and "OpenTelemetry" not in layers \
                and not set(project.code.tracing) & {"aws-xray-sdk", "powertools-tracer", "opentelemetry", "adot"} \
                and not own_emitter:
            path, locator = _where(project, fn)
            report.add("ACR044", "info", "observability",
                       f"{fn.address} ({runtime}) has no ADOT layer and the code imports no tracer: "
                       "DynamoDB, Secrets Manager and HTTP calls will not appear as subsegments",
                       path=path, locator=locator,
                       fix="add the AWSOpenTelemetryDistroJs layer with AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument, "
                           "or Powertools Tracer; the X-Ray SDKs entered maintenance on 2026-02-25.",
                       source="https://aws-otel.github.io/docs/getting-started/lambda")
    for api in project.http_apis():
        path, locator = _where(project, api)
        report.add("ACR045", "info", "observability",
                   f"{api.address} is an HTTP API: API Gateway X-Ray tracing is not available for HTTP APIs",
                   path=path, locator=locator,
                   fix="the Lambda segment is the first one in the trace; compare the access-log "
                       "$context.responseLatency with it to see API Gateway's share. A REST API supports "
                       "active tracing if that hop must be traced.",
                   source=SRC_HTTP_API_XRAY)


def mcp_backend_lambdas(project: Project) -> set[str]:
    """Addresses of the functions behind the MCP endpoint (see :func:`mcp_backend_blocks`)."""
    return {b.address for b in mcp_backend_blocks(project)}


def _lambda_in_dir(project: Project, name: str, directory: Path) -> hcl.Block | None:
    for fn in project.lambdas():
        if fn.name == name and Path(fn.file).resolve().parent == directory:
            return fn
    return None


def mcp_backend_blocks(project: Project) -> list[hcl.Block]:
    """Functions behind the MCP endpoint, as blocks (two modules may both have `aws_lambda_function.mcp`).

    HTTP APIs: route ending in /mcp -> `integrations/${aws_apigatewayv2_integration.X.id}` ->
    `integration_uri = aws_lambda_function.Y.invoke_arn`. REST APIs: an
    `aws_api_gateway_integration` on a resource whose `path_part` is `mcp`, or a
    `{proxy+}` resource when the code holds an MCP server, -> `uri =
    aws_lambda_function.Y.invoke_arn`. Each link is resolved in the module
    directory that declares it. When nothing can be followed and there is
    exactly one function, that function is assumed.
    """
    found: list[hcl.Block] = []

    def keep(fn: hcl.Block | None) -> None:
        if fn is not None and all(fn is not other for other in found):
            found.append(fn)

    routes = project.mcp_routes()
    if routes:
        route_addresses = {r["resource"] for r in routes}
        for route in project.tf.resources_of("aws_apigatewayv2_route"):
            if route.address not in route_addresses:
                continue
            directory = Path(route.file).resolve().parent
            match = re.search(r"aws_apigatewayv2_integration\.([A-Za-z0-9_\-]+)", route.get("target") or "")
            if not match:
                continue
            integration = next((b for b in project.tf.resources_of("aws_apigatewayv2_integration")
                                if b.name == match.group(1) and Path(b.file).resolve().parent == directory), None)
            if integration is None:
                continue
            fn = re.search(r"aws_lambda_function\.([A-Za-z0-9_\-]+)", integration.get("integration_uri") or "")
            if fn:
                keep(_lambda_in_dir(project, fn.group(1), directory))
    for integration in project.tf.resources_of("aws_api_gateway_integration"):
        directory = Path(integration.file).resolve().parent
        res = re.search(r"aws_api_gateway_resource\.([A-Za-z0-9_\-]+)", integration.get("resource_id") or "")
        resource = next((b for b in project.tf.resources_of("aws_api_gateway_resource")
                         if res and b.name == res.group(1) and Path(b.file).resolve().parent == directory), None)
        part = resource.literal("path_part") if resource is not None else None
        if part == "mcp" or (part == "{proxy+}" and project.code.mcp_servers):
            fn = re.search(r"aws_lambda_function\.([A-Za-z0-9_\-]+)", integration.get("uri") or "")
            if fn:
                keep(_lambda_in_dir(project, fn.group(1), directory))
    if not found and (routes or project.rest_apis()) and len(project.lambdas()) == 1:
        found.append(project.lambdas()[0])
    return found


def _transaction_search_evidence(project: Project) -> bool:
    for block in project.tf.resources_of("aws_cloudwatch_log_resource_policy"):
        if "xray.amazonaws.com" in (block.get("policy_document") or "") or "aws/spans" in (block.text or ""):
            return True
    for block in project.tf.blocks:
        if block.kind == "resource" and block.type.startswith("aws_xray_") and "indexing" in block.type:
            return True
    return False


def _gateway_target_lambdas(project: Project) -> set[str]:
    refs: set[str] = set()
    for target in project.gateway_targets():
        lam = target.find("target_configuration", "mcp", "lambda")
        if lam is not None:
            raw = lam.get("lambda_arn") or ""
            match = re.match(r"(aws_lambda_function\.[A-Za-z0-9_\-]+)", raw.strip())
            if match:
                refs.add(match.group(1))
            module_ref = re.match(r"module\.[A-Za-z0-9_]+\.([A-Za-z0-9_]+)", raw.strip())
            if module_ref:
                refs.add(module_ref.group(1))
    return refs


# -- ACR05x ---------------------------------------------------------------

def check_targets(project: Project, report: GapReport) -> None:
    for target in project.gateway_targets():
        path, locator = _where(project, target)
        cfg = target.find("target_configuration", "mcp")
        creds = target.child("credential_provider_configuration")
        if cfg is None:
            if target.find("target_configuration", "http") is None:
                report.add("ACR053", "info", "targets",
                           f"{target.address}: could not read target_configuration",
                           path=path, locator=locator, source=SRC_OUTBOUND)
            continue
        if cfg.child("lambda") is not None:
            if creds is not None and creds.child("gateway_iam_role") is None:
                report.add("ACR051", "error", "targets",
                           f"{target.address}: a Lambda target supports only the gateway service role for outbound auth",
                           path=path, locator=locator,
                           fix="use credential_provider_configuration { gateway_iam_role {} } and grant the "
                               "gateway role lambda:InvokeFunction on the function.",
                           source=SRC_OUTBOUND)
            continue
        server = cfg.child("mcp_server")
        openapi = cfg.child("open_api_schema")
        if (server is not None or openapi is not None) and creds is None:
            report.add("ACR050", "warn", "targets",
                       f"{target.address}: no credential_provider_configuration — the gateway calls the "
                       "upstream with no authorization",
                       path=path, locator=locator,
                       fix="add oauth (client credentials from a Cognito M2M client via an OAuth2 credential "
                           "provider), api_key, or gateway_iam_role (SigV4). AWS calls no-auth \"not recommended\".",
                       source=SRC_MCP_TARGET)
        if server is not None:
            endpoint = hcl.string_or_ref(server.get("endpoint")) or ""
            if endpoint.startswith("http://"):
                report.add("ACR052", "error", "targets",
                           f"{target.address}: MCP server endpoint is plain http: {endpoint}",
                           path=path, locator=locator,
                           fix="serve the upstream over HTTPS.", source=SRC_MCP_TARGET)
            mode = (server.literal("listing_mode") or "DEFAULT").upper()
            gateway_semantic = any(
                (g.find("protocol_configuration", "mcp") and
                 (g.find("protocol_configuration", "mcp").literal("search_type") or "").upper() == "SEMANTIC")
                for g in project.gateways())
            if mode == "DYNAMIC" and gateway_semantic:
                report.add("ACR054", "error", "targets",
                           f"{target.address}: listing_mode DYNAMIC is not interoperable with semantic search",
                           path=path, locator=locator,
                           fix="use DEFAULT (indexed, synchronised) listing or turn semantic search off.",
                           source=SRC_MCP_TARGET)


# -- ACR06x ---------------------------------------------------------------

def check_runtime_contract(project: Project, report: GapReport) -> None:
    uses_runtime = bool(project.runtimes()) or bool(project.code.entrypoints) or bool(project.code.agentcore_sdk)
    if not uses_runtime:
        return
    protocols = {((r.find("protocol_configuration").literal("server_protocol") if r.find("protocol_configuration") else None) or "HTTP").upper()
                 for r in project.runtimes()} or {"HTTP"}
    for docker in project.code.dockerfiles:
        if not docker.get("arm64"):
            report.add("ACR060", "error", "runtime",
                       f"{docker['file']} does not build for linux/arm64",
                       path=docker["file"],
                       fix="AgentCore Runtime requires an ARM64 container: `FROM --platform=linux/arm64 ...` "
                           "or `docker buildx build --platform linux/arm64`.",
                       source=SRC_HTTP_CONTRACT)
        expected = {"HTTP": "8080", "AGUI": "8080", "MCP": "8000", "A2A": "9000"}
        wanted = {expected[p] for p in protocols if p in expected}
        if docker.get("expose") and wanted and not wanted & set(docker["expose"]):
            report.add("ACR063", "warn", "runtime",
                       f"{docker['file']} exposes {', '.join(docker['expose'])}; the {'/'.join(sorted(protocols))} "
                       f"contract listens on {', '.join(sorted(wanted))}",
                       path=docker["file"], fix="listen on 0.0.0.0 at the contract port.",
                       source=f"{DOCS}/runtime-service-contract.html")
    if "HTTP" in protocols and "/ping" not in project.code.routes and not project.code.mcp_servers:
        report.add("ACR061", "warn", "runtime",
                   "no GET /ping handler found for an HTTP-protocol runtime",
                   path=str(project.root),
                   fix="serve GET /ping returning {\"status\": \"Healthy\"} (or HealthyBusy while async work "
                       "runs). BedrockAgentCoreApp provides it; a hand-written server must.",
                   source=SRC_HTTP_CONTRACT)
    py_mcp = [s for s in project.code.mcp_servers if s["kind"].startswith("python")]
    if ("MCP" in protocols or py_mcp) and py_mcp and not project.code.stateless_http:
        report.add("ACR062", "warn", "runtime",
                   "a Python MCP server for Runtime does not set stateless_http=True",
                   path=py_mcp[0]["file"],
                   fix="the platform adds its own Mcp-Session-Id; a stateful server may reject it. Use "
                       "FastMCP(..., stateless_http=True) with streamable-http on 0.0.0.0:8000/mcp.",
                   source=SRC_MCP_CONTRACT)


# -- ACR07x ---------------------------------------------------------------

def check_protocol_pinning(project: Project, report: GapReport) -> None:
    for gateway in project.gateways():
        path, locator = _where(project, gateway)
        cfg = gateway.find("protocol_configuration", "mcp")
        versions = cfg.literal("supported_versions") if cfg is not None else None
        if cfg is not None and cfg.get("supported_versions") and versions is None:
            continue  # pinned through a variable or local: resolved at plan time
        if not versions:
            report.add("ACR070", "info", "protocol",
                       f"{gateway.address} does not pin protocol_configuration.mcp.supported_versions",
                       path=path, locator=locator,
                       fix="pin the revisions you test against (e.g. [\"2025-11-25\", \"2026-07-28\"]); "
                           "2026-07-28 is opt-in and requests without a version header are treated as 2025-03-26.",
                       source=SRC_GATEWAY_USING)
        elif isinstance(versions, list):
            unknown = [v for v in versions if v not in data.mcp_versions()["gateway_inbound"]]
            if unknown:
                report.add("ACR071", "error", "protocol",
                           f"{gateway.address} lists MCP revisions Gateway does not support: {', '.join(unknown)}",
                           path=path, locator=locator,
                           fix=f"supported: {', '.join(data.mcp_versions()['gateway_inbound'])}",
                           source=SRC_GATEWAY_USING)


# -- ACR08x ---------------------------------------------------------------

def check_memory(project: Project, report: GapReport) -> None:
    for memory in project.memories():
        path, locator = _where(project, memory)
        days = memory.literal("event_expiry_duration")
        if isinstance(days, int) and not 7 <= days <= 365:
            report.add("ACR080", "error", "memory",
                       f"{memory.address} event_expiry_duration {days} is outside 7..365 days",
                       path=path, locator=locator, fix="choose 7 to 365 days.", source=SRC_MEMORY_TF)
        if not memory.has("encryption_key_arn"):
            report.add("ACR081", "info", "memory",
                       f"{memory.address} uses an AWS-managed key",
                       path=path, locator=locator,
                       fix="for conversations that may hold personal data, set encryption_key_arn to a "
                           "customer-managed KMS key; event metadata is never CMK-encrypted, so keep PII out of it.",
                       source=SRC_MEMORY)
    strategies: dict[str, int] = {}
    for strategy in project.tf.resources_of("aws_bedrockagentcore_memory_strategy"):
        key = strategy.get("memory_id") or "?"
        strategies[key] = strategies.get(key, 0) + 1
    for memory_ref, count in strategies.items():
        if count > data.quota("memory.strategies_per_memory"):
            report.add("ACR082", "error", "memory",
                       f"{count} strategies on {memory_ref}; the limit is {data.quota('memory.strategies_per_memory')}",
                       path=str(project.root), fix="merge or drop strategies.",
                       source=data.quotas()["source"])


# -- ACR09x ---------------------------------------------------------------

def check_tooling(project: Project, report: GapReport) -> None:
    from .project import provider_version

    if project.agentcore_resources():
        version = provider_version(project)
        locked = hcl.version_tuple(version["locked"])
        if locked and locked < hcl.version_tuple(PROVIDER_MIN_ASSUMED):
            report.add("ACR090", "warn", "tooling",
                       f"hashicorp/aws is locked at {version['locked']}; this plugin's Terraform assumes "
                       f">= {PROVIDER_MIN_ASSUMED}",
                       path=str(project.root),
                       fix="terraform init -upgrade within your constraint, then re-plan.",
                       source=SRC_TF_CHANGELOG)
    for config in project.code.starter_toolkit_configs:
        report.add("ACR095", "warn", "tooling",
                   f"{config}: the bedrock-agentcore-starter-toolkit CLI is no longer supported",
                   path=config,
                   fix="move to Terraform (this plugin) or the AgentCore CLI (`npm install -g @aws/agentcore`).",
                   source=SRC_STARTER)


__all__ = ["run_all", "DOCS_CHECKED"]
