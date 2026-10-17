#!/usr/bin/env python3
"""Plan an AgentCore deploy: sequencing, quotas, the commands, and the way back.

This never runs Terraform, Terragrunt or the AWS CLI. It reads the project,
finds the root module that owns the AgentCore resources, and emits:

* the order things come up in (identity and roles before the gateway, the
  gateway before its targets, Transaction Search before TRACES delivery) and
  where a first apply typically trips (IAM propagation, creation-only
  settings such as semantic search);
* quota checks against the published AgentCore quotas (targets per gateway,
  tools per target, memory strategies) — DPL0xx findings;
* the exact commands to init, validate, plan to a file, export the plan as
  JSON, run the plan policy, and apply that saved plan — for you to run after
  you have read the plan;
* the rollback for each kind of change.

    deploy_plan.py <project> [--root DIR] [--plan-file agentcore.tfplan] [--json] [--dry-run]

Every fact is read from the chosen root (--root, relative to the project, or
the discovered one): its stages and quotas from its own files and the local
modules it calls, the hashicorp/aws constraint from its own
required_providers and the locked version from its own .terraform.lock.hcl
("not locked yet" before the first init) — never from a sibling environment.
Commands address the plugin as $AGENTCORE_PLUGIN (`setup` sets it from
CLAUDE_PLUGIN_ROOT), not by this machine's install path.

--dry-run is accepted for symmetry and changes nothing: this script only ever
prints. Exit codes: 0 no errors, 1 errors (e.g. a quota exceeded), 2 no
Terraform found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a read-only plugin install must stay clean: no __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from agentcore_skills import PROVIDER_MIN_ASSUMED, cli, data, hcl  # noqa: E402
from agentcore_skills.project import load, provider_version  # noqa: E402
from agentcore_skills.report import EXIT_USAGE, GapReport, Option, exit_code_for  # noqa: E402

STAGES = [
    ("identity", ("aws_cognito_", "aws_kms_key", "aws_bedrockagentcore_workload_identity",
                  "aws_bedrockagentcore_oauth2_credential_provider", "aws_bedrockagentcore_api_key_credential_provider",
                  "aws_bedrockagentcore_token_vault_cmk")),
    ("roles", ("aws_iam_role", "aws_iam_role_policy", "aws_iam_policy", "aws_iam_role_policy_attachment")),
    ("core", ("aws_ecr_repository", "aws_bedrockagentcore_gateway", "aws_bedrockagentcore_agent_runtime",
              "aws_bedrockagentcore_memory", "aws_bedrockagentcore_code_interpreter", "aws_bedrockagentcore_browser")),
    ("attachments", ("aws_bedrockagentcore_gateway_target", "aws_bedrockagentcore_memory_strategy",
                     "aws_bedrockagentcore_agent_runtime_endpoint", "aws_bedrockagentcore_gateway_rule")),
    ("telemetry", ("aws_cloudwatch_log_group", "aws_cloudwatch_log_delivery", "aws_cloudwatch_log_delivery_",
                   "aws_cloudwatch_log_resource_policy", "aws_xray_", "aws_cloudwatch_metric_alarm")),
    ("guardrails", ("aws_budgets_budget",)),
]


def stage_of(resource_type: str) -> str | None:
    for name, prefixes in STAGES:
        # an entry ending in "_" is a prefix; anything else must match exactly,
        # so aws_bedrockagentcore_gateway never swallows ..._gateway_target
        if any(resource_type == p or (p.endswith("_") and resource_type.startswith(p)) for p in prefixes):
            return name
    return None


def reachable_dirs(project, root: Path, seen: set[Path] | None = None) -> set[Path]:
    """The root and every local module directory it calls, transitively."""
    seen = seen if seen is not None else set()
    root = root.resolve()
    if root in seen:
        return seen
    seen.add(root)
    for call in project.tf.of_kind("module"):
        if Path(call.file).resolve().parent != root:
            continue
        source = hcl.literal(call.get("source") or '""')
        if isinstance(source, str) and source.startswith("."):
            reachable_dirs(project, (root / source), seen)
    return seen


def find_roots(project) -> list[Path]:
    """Root modules, best first: the one that reaches the most AgentCore resources.

    A root is a directory with a provider block, a backend, or a terragrunt.hcl.
    Ties go to the root that reaches more resources overall, so a bootstrap
    state stack never wins over the application stack.
    """
    roots: set[Path] = set()
    for block in project.tf.blocks:
        if block.kind == "provider" or (block.kind == "terraform" and block.child("backend") is not None):
            roots.add(Path(block.file).parent)
    if project.root.is_dir():
        for path in project.root.rglob("terragrunt.hcl"):
            if ".terragrunt-cache" not in path.parts:
                roots.add(path.parent)

    def score(root: Path) -> tuple[int, int, str]:
        dirs = reachable_dirs(project, root)
        resources = [b for b in project.tf.blocks if b.kind == "resource" and Path(b.file).resolve().parent in dirs]
        agentcore = sum(1 for b in resources if b.type.startswith(("aws_bedrockagentcore_", "awscc_bedrockagentcore_")))
        return (-agentcore, -len(resources), str(root))

    return sorted(roots, key=score)


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--root", help="the root module directory to plan (default: discovered)")
    parser.add_argument("--plan-file", default="agentcore.tfplan")
    parser.add_argument("--dry-run", action="store_true", help="accepted for symmetry; this script only prints")
    cli.add_format(parser)
    args = parser.parse_args(argv)
    target = Path(args.project).expanduser()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return EXIT_USAGE
    project = load(target)
    if not project.tf.files:
        print(f"error: no Terraform under {target}", file=sys.stderr)
        return EXIT_USAGE
    report = GapReport(subject=str(project.root), skill="agentcore-deploy")
    roots = find_roots(project)
    if args.root:
        root = Path(args.root).expanduser()
        root = root if root.is_absolute() else (target / root if (target / root).is_dir() else root)
        if not root.is_dir():
            print(f"error: --root {args.root} is not a directory", file=sys.stderr)
            return EXIT_USAGE
    else:
        root = roots[0] if roots else project.root
    # Everything below describes the chosen root: its own files and the local
    # modules it calls, its own required_providers and lock, its own region.
    scoped = load(target, env=root.resolve())
    terragrunt = (root / "terragrunt.hcl").is_file()
    tool = "terragrunt" if terragrunt else f"terraform -chdir={project.rel(root)}"

    # -- staging ---------------------------------------------------------------
    staged: dict[str, list[str]] = {name: [] for name, _ in STAGES}
    agentcore_dirs = {Path(b.file).resolve().parent for b in scoped.agentcore_resources()}
    for block in scoped.tf.blocks:
        if block.kind == "resource":
            stage = stage_of(block.type)
            if stage and Path(block.file).resolve().parent in agentcore_dirs:
                staged[stage].append(block.address)
    agentcore = scoped.agentcore_resources()

    # -- findings ----------------------------------------------------------------
    has_backend = any(b.kind == "terraform" and b.child("backend") is not None for b in scoped.tf.blocks) or terragrunt
    if not has_backend:
        report.add("DPL001", "warn", "state", "no remote backend: state for the gateway and its credentials lives on one laptop",
                   path=project.rel(root), fix="configure an S3 backend with use_lockfile = true before the first apply.",
                   source="https://developer.hashicorp.com/terraform/language/backend/s3")
    per_gateway: dict[str, int] = {}
    for target_block in scoped.gateway_targets():
        ref = target_block.get("gateway_identifier") or "?"
        per_gateway[ref] = per_gateway.get(ref, 0) + 1
        lam = target_block.find("target_configuration", "mcp", "lambda", "tool_schema")
        if lam is not None and len(lam.children("inline_payload")) > data.quota("gateway.tools_per_target"):
            report.add("DPL002", "error", "quota", f"{target_block.address} declares more tools than the per-target quota",
                       fix="split the target or request a quota increase.", source=data.quotas()["source"])
    for ref, count in per_gateway.items():
        if count > data.quota("gateway.targets_per_gateway"):
            report.add("DPL002", "error", "quota", f"{count} targets on {ref}; the quota is "
                       f"{data.quota('gateway.targets_per_gateway')}", fix="request an increase first (adjustable).",
                       source=data.quotas()["source"])
    if len(scoped.gateways()) > 0 and staged["roles"]:
        report.add("DPL003", "info", "sequencing",
                   "the gateway role and the gateway are created in one apply; a fresh IAM role can take seconds to "
                   "propagate, and a first apply may fail on the target with an access error",
                   fix="re-run the same apply; if it repeats, add depends_on from the target to the role policy.",
                   source="https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_general.html#troubleshoot_general_eventual-consistency")
    for gateway in scoped.gateways():
        cfg = gateway.find("protocol_configuration", "mcp")
        if cfg is not None and (cfg.literal("search_type") or "").upper() == "SEMANTIC":
            report.add("DPL004", "info", "sequencing", f"{gateway.address} enables semantic search, which is creation-only",
                       fix="decide now: toggling it later replaces the gateway and changes its URL.",
                       source="https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html")
    version = provider_version(scoped, root_only=True)
    if version["locked"] is None:
        version["locked"] = "not locked yet (run init)"
    if agentcore and version["constraint"] is None:
        report.add("DPL008", "info", "tooling", f"{project.rel(root)} declares no hashicorp/aws version constraint",
                   path=project.rel(root), fix=f'add required_providers {{ aws = {{ source = "hashicorp/aws", '
                   f'version = ">= {PROVIDER_MIN_ASSUMED}" }} }} to the root module.',
                   source="https://developer.hashicorp.com/terraform/language/providers/requirements")
    if agentcore and version["locked"][0].isdigit() and \
            hcl.version_tuple(version["locked"]) < hcl.version_tuple(PROVIDER_MIN_ASSUMED):
        report.add("DPL006", "warn", "tooling", f"hashicorp/aws locked at {version['locked']} (< {PROVIDER_MIN_ASSUMED})",
                   fix=f"{tool} init -upgrade", source="https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md")
    if any((s.literal("log_type") or "") == "TRACES" for s in scoped.tf.resources_of("aws_cloudwatch_log_delivery_source")):
        report.add("DPL007", "info", "sequencing", "TRACES delivery requires CloudWatch Transaction Search to be enabled "
                   "in the account and region first", fix="run transaction-search.sh (from agentcore-observe) once, before the apply.",
                   source="https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html")
    if terragrunt:
        report.add("DPL005", "info", "tooling", f"{project.rel(root)} is a Terragrunt stack; commands use terragrunt",
                   path=project.rel(root))

    plan_json = args.plan_file.replace(".tfplan", ".plan.json")
    # No machine-specific paths in commands a human copies: the plugin is
    # addressed through $AGENTCORE_PLUGIN (Claude Code sets CLAUDE_PLUGIN_ROOT
    # for the plugin's own skills).
    plugin_env = 'export AGENTCORE_PLUGIN="${CLAUDE_PLUGIN_ROOT:-<path to the agentcore plugin>}"'
    policy = 'python3 "$AGENTCORE_PLUGIN/skills/agentcore-ci/scripts/policy_check.py"'
    commands = [
        f"{tool} init -input=false",
        f"{tool} validate",
        f"{tool} plan -input=false -out={args.plan_file}",
        f"{tool} show -json {args.plan_file} > {plan_json}",
        f"{policy} {plan_json}",
        f"# only after a human has read the plan and the policy output:\n{tool} apply {args.plan_file}",
    ]
    post = []
    if scoped.gateways():
        post.append("aws bedrock-agentcore-control list-gateways --query 'items[].{id:gatewayId,status:status,name:name}'")
        post.append('python3 "$AGENTCORE_PLUGIN/skills/agentcore-verify/scripts/verify.py" --gateway-url '
                    "<gateway_url output> --token-env GATEWAY_TOKEN")
    rollback = [
        "a bad target or credential: revert the commit and apply again; the gateway and its URL stay",
        "a bad gateway setting (authorizer, supported_versions): set the previous value and apply; UpdateGateway "
        "replaces supported_versions with exactly the list you send",
        f"remove only the new AgentCore layer: {tool} plan -destroy -target=<address> -out=rollback.tfplan, review, "
        "then apply rollback.tfplan (targets first, then the gateway)",
        "never destroy the Cognito pool, memory or credential providers as part of a rollback: they hold users, "
        "conversations and secrets (the CI policy refuses it)",
    ]
    report.discovered = {
        "root_module": project.rel(root),
        "other_roots": [project.rel(r) for r in roots if r != root],
        "terragrunt": terragrunt,
        "region": scoped.primary_region() or project.primary_region() or "not resolved",
        "aws_provider": version,
        "modules_followed": [project.rel(d) for d in scoped.tf.module_dirs],
        "stages": {k: v for k, v in staged.items() if v},
        "setup": [plugin_env],
        "commands": commands,
        "after_apply": post,
        "rollback": rollback,
    }
    report.add_option(Option(key="1", label="Run the plan yourself, then share the JSON", recommended=True,
                             detail="init/validate/plan/show -json, then policy_check.py; nothing is applied",
                             cost="aws", runs=[plugin_env] + commands[:5]))
    report.add_option(Option(key="2", label="Apply the saved plan", detail="only the reviewed plan file; then verify",
                             cost="aws", runs=[commands[5].splitlines()[-1]]))
    print(report.render(args.format))
    return exit_code_for(report)


if __name__ == "__main__":
    raise SystemExit(main())
