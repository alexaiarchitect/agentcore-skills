#!/usr/bin/env python3
"""Plan an AgentCore Gateway in front of an existing Lambda, HTTP API or MCP server.

The decision this script makes explicit is the target type, because it decides
what has to change upstream:

* an MCP server target (--upstream mcp) points the gateway at an MCP endpoint
  you already serve over HTTPS (for example API Gateway -> Lambda at /mcp).
  Nothing upstream changes except that it must accept the gateway's outbound
  credential. This is the recommended path when the upstream already speaks MCP.
* a Lambda target (--upstream lambda) invokes a function directly with the
  tool arguments as the event and the tool name in
  context.client_context.custom.bedrockAgentCoreToolName ("<target>___<tool>").
  An existing MCP-over-HTTP Lambda does not speak that contract; it needs an
  adapter handler. GWY003 says so when it sees one.
* an OpenAPI target (--upstream openapi) turns REST operations into tools.

Inbound is always a JWT authorizer (CUSTOM_JWT): the Cognito discovery URL
and allowed_clients are resolved from the project's Terraform when a user pool
exists. Outbound defaults to OAuth client credentials through an AgentCore
Identity credential provider (--with-identity writes that module too;
--client-ref reuses an existing Cognito client for it). MCP revisions are
pinned (default 2025-11-25 and the opt-in 2026-07-28).

Identity propagation (GWY002): with client-credentials outbound the upstream
sees the gateway, not the user. --interceptor adds a REQUEST interceptor:

* forward-jwt   generate a Lambda that copies the caller's already-validated
                bearer token into params._meta[--meta-key]; the upstream
                re-verifies it (no shared secret) — option C;
* signed-claim  generate a Lambda that signs a short-lived HS256 claim (sub,
                issuer, client, scope) with a Secrets Manager key — option C';
* <lambda ARN>  wire an interceptor you already have.

Either way the gateway gets interceptor_configuration (REQUEST,
pass_request_headers = true) and its role may lambda:InvokeFunction it; the
generated modes also write modules/agentcore-gateway-interceptor (source, role,
log group, function).

--out-dir DIR is the *modules* directory: the gateway goes to
DIR/agentcore-gateway, and --with-identity / --interceptor add
DIR/agentcore-identity and DIR/agentcore-gateway-interceptor beside it (the
default DIR is infrastructure/modules or terraform/modules).

    gateway_plan.py <project> [--upstream auto|mcp|lambda|openapi] [--endpoint URL]
                    [--name NAME] [--outbound oauth|api_key|iam|none]
                    [--versions 2025-11-25,2026-07-28] [--semantic] [--tools tools.json]
                    [--with-identity [--client-ref aws_cognito_user_pool_client.x]]
                    [--interceptor forward-jwt|signed-claim|<lambda arn> [--meta-key KEY]]
                    [--out-dir DIR] [--dry-run] [--force] [--json]

Findings are the GWY0xx band. Writes Terraform only without --dry-run, and
never plans or applies it. Exit codes: 0 planned/written, 1 an error finding,
2 bad arguments.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DOCS_CHECKED, cli, data, hcl, tfgen  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.rules import mcp_backend_lambdas  # noqa: E402
from agentcore_skills.templating import WritePlan  # noqa: E402

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"


def resolve_endpoint(project) -> str | None:
    """`https://<custom domain>/mcp` from an API Gateway domain name, if resolvable."""
    for block in project.tf.resources_of("aws_apigatewayv2_domain_name"):
        raw = block.get("domain_name") or ""
        value = hcl.literal(raw)
        if not isinstance(value, str):
            ref = re.fullmatch(r"var\.([A-Za-z0-9_]+)", raw.strip())
            value = project.tf.variable_default(ref.group(1)) if ref else None
        if isinstance(value, str) and "." in value:
            return f"https://{value}/mcp"
    return None


def cognito_wiring(project, pools) -> tuple[str, str]:
    """Root-module expressions for discovery_url and allowed_clients.

    Prefers outputs the Cognito module already exposes (an issuer URL, a list
    of client ids), because the pool usually lives in a child module and the
    root cannot address its resources directly.
    """
    if not pools:
        return ('"https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration"', '["<client id>"]')
    pool = pools[0]
    call = project.module_call_for(pool)
    if call:
        outputs = project.outputs_in_dir_of(pool)
        issuer = next((n for n, v in outputs.items() if f"{pool.address}.endpoint" in v), None)
        pool_id = next((n for n, v in outputs.items() if v.strip() == f"{pool.address}.id"), None)
        lists = [n for n, v in outputs.items() if "aws_cognito_user_pool_client" in v and ("[*]" in v or "concat" in v)]
        if issuer:
            discovery = f'"${{module.{call}.{issuer}}}/.well-known/openid-configuration"'
        elif pool_id:
            discovery = f'"https://cognito-idp.${{var.aws_region}}.amazonaws.com/${{module.{call}.{pool_id}}}/.well-known/openid-configuration"'
        else:
            discovery = f'"https://cognito-idp.<region>.amazonaws.com/${{module.{call}.<pool id output>}}/.well-known/openid-configuration"'
        clients = f"module.{call}.{lists[0]}" if lists else f"module.{call}.<client ids output>"
        return discovery, clients
    clients = [project.ref_expr(b) for b in project.tf.resources_of("aws_cognito_user_pool_client")]
    joined = clients[0] if len(clients) == 1 and clients[0].startswith("values(") else "[" + ", ".join(clients[:3]) + "]"
    return (f'"https://cognito-idp.${{var.aws_region}}.amazonaws.com/${{{pool.address}.id}}/.well-known/openid-configuration"',
            joined if clients else '["<client id>"]')


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--upstream", choices=("auto", "mcp", "lambda", "openapi"), default="auto")
    parser.add_argument("--endpoint", help="HTTPS URL of the existing MCP endpoint (mcp upstream)")
    parser.add_argument("--lambda-ref", help="Terraform address of the tool Lambda (lambda upstream)")
    parser.add_argument("--name", default=None)
    parser.add_argument("--outbound", choices=("oauth", "api_key", "iam", "none"), default=None)
    parser.add_argument("--versions", default="2025-11-25,2026-07-28")
    parser.add_argument("--semantic", action="store_true", help="enable semantic tool search (creation-time only)")
    parser.add_argument("--tools", help="JSON tool list for a Lambda target ([{name, description, properties}])")
    parser.add_argument("--with-identity", action="store_true", help="also write the Cognito M2M outbound identity module")
    parser.add_argument("--client-ref", help="with --with-identity: reuse this existing Cognito app client "
                        "(aws_cognito_user_pool_client.<name>) instead of creating one")
    parser.add_argument("--interceptor", help="forward-jwt | signed-claim (generate the REQUEST interceptor "
                        "Lambda) or the ARN of an existing interceptor Lambda to wire")
    parser.add_argument("--meta-key", default=None,
                        help="params._meta key the interceptor writes (default: <project-name>/end-user-token; "
                             "prefer a reverse-DNS prefix you own, e.g. com.example/end-user-token)")
    parser.add_argument("--out-dir", default=None,
                        help="modules directory; modules go to DIR/agentcore-gateway, DIR/agentcore-identity, "
                             "DIR/agentcore-gateway-interceptor")
    cli.add_writer(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    project = load(root)
    report = GapReport(subject=str(project.root), skill="agentcore-gateway")
    region = project.primary_region()
    mcp_lambdas = sorted(mcp_backend_lambdas(project))
    endpoint = args.endpoint or resolve_endpoint(project)

    upstream = args.upstream
    if upstream == "auto":
        upstream = "mcp" if (project.mcp_routes() or project.code.mcp_servers) else "lambda"
    outbound = args.outbound or ("iam" if upstream == "lambda" else "oauth")
    if upstream == "lambda":
        outbound = "iam"

    unknown = [v for v in versions if v not in data.mcp_versions()["gateway_inbound"]]
    if unknown:
        report.add("GWY007", "error", "protocol", f"unsupported MCP revision(s): {', '.join(unknown)}",
                   fix=f"choose from {', '.join(data.mcp_versions()['gateway_inbound'])}",
                   source=f"{DOCS}/gateway-using.html")
    if upstream == "lambda":
        chosen = args.lambda_ref or (mcp_lambdas[0] if mcp_lambdas else None)
        if chosen and chosen in mcp_lambdas:
            report.add("GWY003", "error", "target",
                       f"{chosen} serves MCP over API Gateway; a Lambda target invokes it with tool arguments "
                       "as the event, which that handler does not understand",
                       fix="use --upstream mcp (point the gateway at the existing /mcp endpoint), or write a "
                           "separate adapter Lambda that maps bedrockAgentCoreToolName to your tool functions.",
                       source=f"{DOCS}/gateway-add-target-lambda.html")
    if upstream == "mcp" and not endpoint:
        report.add("GWY006", "warn", "target", "no MCP endpoint URL resolved; upstream_endpoint is left as a placeholder",
                   fix="pass --endpoint https://<host>/mcp", source=f"{DOCS}/gateway-target-MCPservers.html")
    if upstream == "mcp" and outbound == "oauth" and not args.interceptor:
        report.add("GWY002", "warn", "identity",
                   "with client-credentials outbound auth every gateway call reaches the upstream as one machine "
                   "principal: an upstream that derives the owner from the token subject sees the gateway, not the user",
                   fix="decide identity propagation before applying: --interceptor forward-jwt generates the "
                       "interceptor that carries the user's validated token in params._meta (option C); "
                       "--interceptor signed-claim signs a user claim instead; see references/identity-propagation.md "
                       "in agentcore-identity for token exchange and Runtime hosting.",
                   source=f"{DOCS}/gateway-outbound-auth.html")
        if project.jwt_authorizers():
            report.add("GWY001", "info", "identity",
                       f"the upstream's API Gateway JWT authorizer ({project.jwt_authorizers()[0].address}) must accept "
                       "the gateway's outbound client id in its audience list",
                       fix="add the outbound client id (module output outbound_client_id) to the authorizer's "
                           "jwt_configuration.audience and to the handler's allowed clients.",
                       source="https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html")
    if "2026-07-28" in versions and upstream == "mcp":
        report.add("GWY005", "info", "protocol",
                   "the gateway will accept 2026-07-28 clients and translate for a 2025-* upstream; that translation "
                   "does not carry elicitation or sampling",
                   source="https://aws.amazon.com/blogs/machine-learning/how-agentcore-gateway-supports-the-mcp-2026-07-28-spec/")
    if args.semantic:
        if region and data.service_available("gateway_semantic_search", region) is False:
            report.add("GWY004", "error", "search", f"semantic search is not offered in {region}",
                       source=f"{DOCS}/gateway-using-mcp-semantic-search.html")
        report.add("GWY008", "info", "search", "semantic search can only be enabled when the gateway is created",
                   fix="turning it on later means a new gateway and a new URL for every client.",
                   source=f"{DOCS}/gateway-create.html")
    pools = project.cognito_pools()
    if not pools:
        report.add("GWY009", "warn", "identity", "no Cognito user pool found; discovery_url and allowed_clients are "
                   "left for you to supply", source=f"{DOCS}/identity-getting-started-cognito.html")

    tools = None
    if args.tools:
        try:
            tools = json.loads(Path(args.tools).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"error: --tools: {exc}", file=sys.stderr)
            return EXIT_USAGE

    interceptor_mode = None
    interceptor_arn = None
    if args.interceptor:
        if args.interceptor in tfgen.INTERCEPTOR_MODES:
            interceptor_mode = args.interceptor
        elif args.interceptor.startswith("arn:") and ":lambda:" in args.interceptor:
            interceptor_arn = args.interceptor
        else:
            print(f"error: --interceptor must be {' or '.join(tfgen.INTERCEPTOR_MODES)} or a Lambda function ARN",
                  file=sys.stderr)
            return EXIT_USAGE
        if upstream == "lambda":
            report.add("GWY016", "warn", "identity",
                       "an interceptor on a Lambda-target gateway: the Lambda already receives the tool call; "
                       "identity reaches it through the event, not params._meta",
                       fix="keep --interceptor for MCP-server targets.", source=f"{DOCS}/gateway-interceptors.html")
    reused = None
    if args.client_ref:
        reused = next((c for c in project.tf.resources_of("aws_cognito_user_pool_client")
                       if c.address == args.client_ref), None)
        if reused is None:
            print(f"error: --client-ref {args.client_ref} is not an aws_cognito_user_pool_client in {root}",
                  file=sys.stderr)
            return EXIT_USAGE

    name = args.name or tfgen.aws_name(f"{root.resolve().name}-gateway")
    files = tfgen.gateway_module(name=name, upstream=upstream, checked=DOCS_CHECKED, semantic=args.semantic,
                                 versions=versions, tools=tools, endpoint=endpoint, outbound=outbound,
                                 interceptor=bool(args.interceptor))
    plan = WritePlan()
    modules = cli.modules_root(root, args.out_dir)
    out = modules / "agentcore-gateway"
    for rel, content in files.items():
        plan.add(out / rel, content, force=args.force)
    identity_written = False
    if args.with_identity:
        if upstream in ("mcp", "openapi") and outbound == "oauth":
            ident = tfgen.identity_module(recipe="cognito-m2m-outbound", name=name, checked=DOCS_CHECKED,
                                          pool_ref=None, resource_server=None, scopes=[],
                                          existing_client=reused is not None)
            for rel, content in ident.items():
                plan.add(modules / "agentcore-identity" / rel, content, force=args.force)
            identity_written = True
        else:
            report.add("GWY015", "warn", "identity",
                       f"--with-identity was not applied: outbound is {outbound} for a {upstream} upstream, and the "
                       "identity module is the Cognito client-credentials (oauth) recipe",
                       fix="use --outbound oauth with an mcp or openapi upstream, or run identity_plan.py with the "
                           "recipe you need.", source=f"{DOCS}/gateway-outbound-auth.html")
    # An MCP `_meta` key prefix is one or more DNS-style labels; prefer a reverse-DNS name you own.
    meta_key = args.meta_key or f"{tfgen.aws_name(root.resolve().name).lower()}/end-user-token"
    if interceptor_mode:
        for rel, content in tfgen.interceptor_module(name=name, mode=interceptor_mode, checked=DOCS_CHECKED,
                                                     meta_key=meta_key).items():
            plan.add(modules / "agentcore-gateway-interceptor" / rel, content, force=args.force)
        report.add("GWY017", "info", "identity",
                   f"the {interceptor_mode} interceptor writes params._meta[\"{meta_key}\"] on every request; the "
                   "upstream must read it, verify it, honour it only when the request's own bearer token is the "
                   "gateway's outbound client, and strip it before the MCP SDK sees the request",
                   fix="see agentcore-identity references/identity-propagation.md, option C; confirm after the first "
                       "apply that two users through the gateway show two owners (whether the gateway keeps "
                       "params._meta for MCP-server targets is not documented).",
                   source=f"{DOCS}/gateway-interceptors-types.html")

    discovery_expr, clients_expr = cognito_wiring(project, pools)
    wiring = f"""module "agentcore_gateway" {{
  source             = "<relative path to {out.name}>"
  discovery_url      = {discovery_expr}
  allowed_clients    = {clients_expr}
  supported_versions = {tfgen.hcl_list(versions)}"""
    if upstream == "mcp":
        wiring += f'\n  upstream_endpoint  = "{endpoint or "https://<host>/mcp"}"'
        if outbound == "oauth":
            wiring += "\n  oauth_provider_arn    = module.agentcore_identity.oauth_provider_arn\n  credential_secret_arn = module.agentcore_identity.credential_secret_arn"
    if interceptor_mode:
        wiring += "\n  interceptor_lambda_arn = module.agentcore_gateway_interceptor.function_arn"
    elif interceptor_arn:
        wiring += f'\n  interceptor_lambda_arn = "{interceptor_arn}"' 
    if upstream == "lambda":
        wiring += f"\n  lambda_arn         = {(args.lambda_ref or '<aws_lambda_function.x>')}.arn"
    wiring += "\n}"
    if identity_written:
        wiring += ('\n\nmodule "agentcore_identity" {\n  source       = "<relative path to agentcore-identity>"'
                   '\n  name         = "' + name + '"\n  user_pool_id = <pool id>')
        if reused is not None:
            wiring += (f"\n  client_id     = {project.ref_expr(reused, 'id')}"
                       f"\n  client_secret = {project.ref_expr(reused, 'client_secret')}")
        else:
            wiring += "\n  oauth_scopes = [\"<resource-server-identifier>/<scope>\"]"
        wiring += "\n}"
    if interceptor_mode:
        wiring += ('\n\nmodule "agentcore_gateway_interceptor" {\n  source   = "<relative path to '
                   'agentcore-gateway-interceptor>"\n  name     = "' + name + '"\n  meta_key = "' + meta_key + '"')
        if interceptor_mode == "signed-claim":
            wiring += ("\n  signing_secret_arn = <aws_secretsmanager_secret.x.arn>"
                       "\n  claim_issuer       = \"<gateway url>\"\n  claim_audience     = \"" +
                       (endpoint or "https://<host>/mcp") + "\"")
        wiring += "\n}"
    report.discovered = {
        "region": region or "not resolved",
        "upstream": upstream,
        "endpoint": endpoint,
        "outbound": outbound,
        "supported_versions": versions,
        "mcp_backend_lambdas": mcp_lambdas,
        "cognito_pools": [b.address for b in pools],
        "semantic_search": args.semantic,
        "modules_dir": str(modules),
        "modules": sorted({Path(i.path).parent.name if Path(i.path).parent.name != "src" else
                           Path(i.path).parent.parent.name for i in plan.items}),
        "interceptor": interceptor_mode or interceptor_arn or "none",
        **({"meta_key": meta_key} if interceptor_mode else {}),
        **({"client_ref": reused.address} if reused is not None else {}),
    }
    notes = ["wire the module from your root module:\n\n```hcl\n" + wiring + "\n```",
             "check tool names: scripts/tool_names.py --from-code <server src> --target-name <target_name>",
             "then /agentcore:agentcore-review, and /agentcore:agentcore-deploy for the plan and apply commands"]
    return cli.finish_plan(plan, fmt=args.format, dry_run=args.dry_run, report=report, notes=notes,
                           extra={"wiring": wiring})


if __name__ == "__main__":
    raise SystemExit(main())
