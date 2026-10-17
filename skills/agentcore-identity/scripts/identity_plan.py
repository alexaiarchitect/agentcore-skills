#!/usr/bin/env python3
"""Plan AgentCore Identity: inbound JWT from Cognito, outbound credentials, workload identity.

AgentCore Identity has two directions and they are configured in different
places, which is where most mistakes start:

* inbound — who may call a gateway or runtime. Nothing is created in
  AgentCore: the gateway's custom_jwt_authorizer trusts an issuer through its
  OIDC discovery URL and checks client_id (allowed_clients), aud
  (allowed_audience), scopes and custom claims. Recipe: cognito-inbound.
* outbound — what the gateway or agent presents to the upstream. A credential
  provider in the token vault holds an OAuth client (CustomOauth2 pointed at
  Cognito's discovery URL) or an API key. Recipes: cognito-m2m-outbound,
  api-key-outbound.
* workload-identity — a standalone identity for an agent not hosted on
  Runtime (Runtime and Gateway create their own).

The script reads the project's Cognito pools, clients and resource servers,
reports what a recipe will rely on (IDN0xx), and writes a Terraform module plus
the equivalent `aws bedrock-agentcore-control` commands. The credential
provider takes secrets through write-only arguments (client_secret_wo,
api_key_wo), so the provider resource keeps them out of state; a Cognito app
client resource still stores its generated client_secret in state, so protect
the state backend either way.

cognito-m2m-outbound creates a dedicated client by default. `--client-ref
aws_cognito_user_pool_client.<name>` reuses one the project already has: the
module then takes `client_id` / `client_secret` inputs and the wiring passes
that client's attributes (through a module output when it lives in a module).

    identity_plan.py <project> --recipe cognito-inbound|cognito-m2m-outbound|api-key-outbound|workload-identity
                     [--name NAME] [--pool-ref aws_cognito_user_pool.x] [--scopes a,b]
                     [--client-ref aws_cognito_user_pool_client.x]
                     [--out-dir DIR] [--dry-run] [--force] [--json]

Exit codes: 0 planned/written, 1 an error finding, 2 bad arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import DOCS_CHECKED, cli, hcl, tfgen  # noqa: E402
from agentcore_skills.project import load  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport  # noqa: E402
from agentcore_skills.templating import WritePlan  # noqa: E402

DOCS = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide"
RECIPES = ("cognito-inbound", "cognito-m2m-outbound", "api-key-outbound", "workload-identity")


def cli_equivalent(recipe: str, name: str, region: str) -> list[str]:
    discovery = f"https://cognito-idp.{region}.amazonaws.com/$USER_POOL_ID/.well-known/openid-configuration"
    if recipe == "cognito-inbound":
        return [f'ISSUER_URL="{discovery}"',
                "# pass $ISSUER_URL as customJWTAuthorizer.discoveryUrl and the app client ids as allowedClients"]
    if recipe == "cognito-m2m-outbound":
        return [
            f"aws cognito-idp create-user-pool-client --user-pool-id $USER_POOL_ID --client-name {name}-gateway-outbound \\\n"
            "  --generate-secret --allowed-o-auth-flows client_credentials --allowed-o-auth-flows-user-pool-client \\\n"
            "  --allowed-o-auth-scopes <resource-server>/<scope>",
            f"aws bedrock-agentcore-control create-oauth2-credential-provider --name {name}-cognito \\\n"
            "  --credential-provider-vendor CustomOauth2 \\\n"
            "  --oauth2-provider-config-input '{\"customOauth2ProviderConfig\": {\"oauthDiscovery\": "
            f"{{\"discoveryUrl\": \"{discovery}\"}}, \"clientId\": \"$CLIENT_ID\", \"clientSecret\": \"$CLIENT_SECRET\"}}}}'",
        ]
    if recipe == "api-key-outbound":
        return [f"aws bedrock-agentcore-control create-api-key-credential-provider --name {name}-api-key --api-key \"$API_KEY\""]
    return [f"aws bedrock-agentcore-control create-workload-identity --name {name}"]


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--recipe", required=True, choices=RECIPES)
    parser.add_argument("--name", default=None)
    parser.add_argument("--pool-ref", help="Terraform address of the user pool, e.g. aws_cognito_user_pool.vault")
    parser.add_argument("--scopes", default="", help="comma-separated scope names on the resource server")
    parser.add_argument("--client-ref", help="cognito-m2m-outbound: reuse this existing confidential app client "
                        "(Terraform address, e.g. aws_cognito_user_pool_client.machine) instead of creating one")
    parser.add_argument("--out-dir", default=None)
    cli.add_writer(parser)
    args = parser.parse_args(argv)
    root = Path(args.project).expanduser()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    project = load(root)
    report = GapReport(subject=str(project.root), skill="agentcore-identity")
    name = args.name or tfgen.aws_name(root.resolve().name)
    region = project.primary_region() or "<region>"
    pools = project.cognito_pools()
    clients = project.tf.resources_of("aws_cognito_user_pool_client")
    servers = project.tf.resources_of("aws_cognito_resource_server")
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]

    if args.recipe.startswith("cognito") and not pools and not args.pool_ref:
        report.add("IDN001", "warn", "cognito", "no aws_cognito_user_pool in this project; user_pool_id becomes a variable",
                   fix="pass the pool id from wherever the pool is managed.", source=f"{DOCS}/identity-getting-started-cognito.html")
    if args.recipe == "cognito-inbound":
        public = [c for c in clients if not c.literal("generate_secret")]
        report.add("IDN002", "info", "cognito",
                   "Cognito access tokens carry client_id; aud is present only for app clients using a resource "
                   "binding, and client-credentials tokens never carry it — use allowed_clients, not allowed_audience alone",
                   fix=f"allowed_clients = [{', '.join(c.address + '.id' for c in public[:4]) or '<client ids>'}]",
                   source=f"{DOCS}/gateway-inbound-auth.html")
        if servers:
            report.add("IDN003", "info", "scopes",
                       f"{servers[0].address} defines custom scopes; tokens carry them fully qualified "
                       "(<identifier>/<scope>), and allowed_scopes must match that form",
                       source=f"{DOCS}/gateway-inbound-auth.html")
    reused = None
    if args.client_ref:
        if args.recipe != "cognito-m2m-outbound":
            print("error: --client-ref applies to --recipe cognito-m2m-outbound only", file=sys.stderr)
            return EXIT_USAGE
        reused = next((c for c in clients if c.address == args.client_ref), None)
        if reused is None:
            print(f"error: --client-ref {args.client_ref}: no such aws_cognito_user_pool_client in {root} "
                  f"(found: {', '.join(c.address for c in clients) or 'none'})", file=sys.stderr)
            return EXIT_USAGE
        flows = reused.literal("allowed_oauth_flows") or []
        if "client_credentials" not in flows or reused.literal("generate_secret") is not True:
            report.add("IDN007", "warn", "cognito",
                       f"{reused.address} is not a confidential client_credentials client "
                       f"(allowed_oauth_flows={flows or 'unresolved'}, generate_secret={reused.literal('generate_secret')})",
                       fix="the token vault needs a client id *and* secret that may use client_credentials; "
                           "pick another client or drop --client-ref to create a dedicated one.",
                       source=f"{DOCS}/identity-getting-started-cognito.html")
    if args.recipe == "cognito-m2m-outbound":
        machine = [c for c in clients if "client_credentials" in (c.literal("allowed_oauth_flows") or [])]
        if machine and reused is None:
            report.add("IDN004", "info", "cognito",
                       f"{len(machine)} client-credentials client(s) already exist ({', '.join(c.address for c in machine)}); "
                       "the recipe adds a dedicated one so the gateway's principal is distinguishable in logs",
                       source=f"{DOCS}/gateway-outbound-auth.html")
        if not servers and not scopes:
            report.add("IDN005", "warn", "scopes", "client credentials need at least one custom scope from a "
                       "resource server; none found and --scopes not given",
                       fix="pass --scopes or set oauth_scopes; Cognito refuses a client-credentials client without scopes.",
                       source="https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html")
        report.add("IDN006", "warn", "identity",
                   "the outbound token identifies the gateway, not the end user",
                   fix="if the upstream derives ownership from the token subject, read references/identity-propagation.md "
                       "before choosing this recipe; agentcore-gateway's gateway_plan.py --interceptor forward-jwt "
                       "generates the interceptor (option C) that carries the user's token to the upstream.",
                   source=f"{DOCS}/gateway-outbound-auth.html")
    # The module is written beside, not inside, the module that owns the pool,
    # so references are passed in as variables; a literal identifier is inlined.
    resource_server = None
    if servers and args.recipe == "cognito-m2m-outbound":
        literal = hcl.literal(servers[0].get("identifier") or '""')
        resource_server = literal if isinstance(literal, str) and literal else None
    files = tfgen.identity_module(recipe=args.recipe, name=name, checked=DOCS_CHECKED, pool_ref=None,
                                  resource_server=resource_server if scopes else None, scopes=scopes,
                                  existing_client=reused is not None)
    plan = WritePlan()
    out = cli.module_dir(root, args.out_dir, "agentcore-identity")
    for rel, content in files.items():
        plan.add(out / rel, content, force=args.force)
    commands = cli_equivalent(args.recipe, name, region)
    report.discovered = {"recipe": args.recipe, "region": region,
                         "cognito_pools": [p.address for p in pools],
                         "cognito_clients": [c.address for c in clients],
                         "resource_servers": [s.address for s in servers],
                         "cli_equivalent": commands}
    wiring = None
    if reused is not None:
        wiring = (f'module "agentcore_identity" {{\n  source        = "<relative path to {out.name}>"\n'
                  f'  name          = "{name}"\n'
                  f'  user_pool_id  = <pool id>\n  client_id     = {project.ref_expr(reused, "id")}\n'
                  f'  client_secret = {project.ref_expr(reused, "client_secret")}\n}}')
        report.discovered["client_ref"] = reused.address
    notes = ["CLI equivalent (not run):\n\n```bash\n" + "\n\n".join(commands) + "\n```",
             "outbound credentials are free when used through Runtime or Gateway (Identity pricing)"]
    if wiring:
        notes.insert(0, "wire the module with the existing client:\n\n```hcl\n" + wiring + "\n```")
    return cli.finish_plan(plan, fmt=args.format, dry_run=args.dry_run, report=report, notes=notes,
                           extra={"cli_equivalent": commands, **({"wiring": wiring} if wiring else {})})


if __name__ == "__main__":
    raise SystemExit(main())
