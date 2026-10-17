"""One model of a project, built once and read by every skill.

`load(path)` combines the Terraform reader (`hcl`) and the code reader
(`codescan`) and answers the cross-cutting questions the skills keep asking:
which AWS region does this deploy to, which AgentCore resources already
exist and through which tool (Terraform, CDK, the AgentCore CLI, the starter
toolkit, boto3), where the MCP endpoint is, how inbound auth works today, and
whether anything is traced. Each answer carries where it came from so a report
can cite the file and line instead of asserting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import codescan, hcl

AGENTCORE_TF_PREFIXES = ("aws_bedrockagentcore_", "awscc_bedrockagentcore_")
REGION_RE = re.compile(r"\b((?:us|eu|ap|ca|sa|me|af|il|mx)(?:-gov)?-(?:north|south|east|west|central|northeast|southeast|southwest|northwest)-\d)\b")


@dataclass
class Project:
    root: Path
    tf: hcl.TerraformProject
    code: codescan.CodeFacts
    regions: list[dict[str, str]] = field(default_factory=list)
    env: Path | None = None

    # -- AgentCore ----------------------------------------------------------
    def agentcore_resources(self) -> list[hcl.Block]:
        return [b for b in self.tf.blocks if b.kind == "resource" and b.type.startswith(AGENTCORE_TF_PREFIXES)]

    def gateways(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_bedrockagentcore_gateway", "awscc_bedrockagentcore_gateway")

    def gateway_targets(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_bedrockagentcore_gateway_target", "awscc_bedrockagentcore_gateway_target")

    def runtimes(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_bedrockagentcore_agent_runtime", "awscc_bedrockagentcore_runtime")

    def memories(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_bedrockagentcore_memory", "awscc_bedrockagentcore_memory")

    # -- the surrounding application ------------------------------------------
    def lambdas(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_lambda_function")

    def http_apis(self) -> list[hcl.Block]:
        return [b for b in self.tf.resources_of("aws_apigatewayv2_api")
                if (b.literal("protocol_type") or "").upper() == "HTTP"]

    def rest_apis(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_api_gateway_rest_api")

    def cognito_pools(self) -> list[hcl.Block]:
        return self.tf.resources_of("aws_cognito_user_pool")

    def jwt_authorizers(self) -> list[hcl.Block]:
        return [b for b in self.tf.resources_of("aws_apigatewayv2_authorizer")
                if (b.literal("authorizer_type") or "").upper() == "JWT"]

    def mcp_routes(self) -> list[dict[str, str]]:
        routes = []
        for block in self.tf.resources_of("aws_apigatewayv2_route"):
            keys = [block.literal("route_key")] if block.literal("route_key") else hcl.strings_in(block.get("for_each"))
            for key in keys:
                if isinstance(key, str) and key.rstrip("/").endswith("/mcp"):
                    routes.append({"route": key, "resource": block.address,
                                   "authorization": block.literal("authorization_type") or "NONE"})
        return routes

    def primary_region(self) -> str | None:
        return self.regions[0]["region"] if self.regions else None

    def all_regions(self) -> list[str]:
        seen: list[str] = []
        for entry in self.regions:
            if entry["region"] not in seen:
                seen.append(entry["region"])
        return seen

    def module_call_for(self, block: hcl.Block) -> str | None:
        """Name of the `module "<name>"` call whose source is the block's directory."""
        directory = Path(block.file).resolve().parent
        for call in self.tf.of_kind("module"):
            source = hcl.literal(call.get("source") or '""')
            if isinstance(source, str) and source.startswith("."):
                if (Path(call.file).resolve().parent / source).resolve() == directory:
                    return call.labels[0] if call.labels else None
        return None

    def outputs_in_dir_of(self, block: hcl.Block) -> dict[str, str]:
        directory = Path(block.file).resolve().parent
        return {o.labels[0]: (o.get("value") or "") for o in self.tf.of_kind("output")
                if o.labels and Path(o.file).resolve().parent == directory}

    def ref_expr(self, block: hcl.Block, attribute: str = "id") -> str:
        """How the root module refers to `block.<attribute>` (through a module output if it lives in one)."""
        call = self.module_call_for(block)
        if call:
            for name, value in self.outputs_in_dir_of(block).items():
                if value.strip() == f"{block.address}.{attribute}":
                    return f"module.{call}.{name}"
            return f"module.{call}.<output exposing {block.address}.{attribute}>"
        if block.get("for_each") or block.get("count"):
            return f"values({block.address})[*].{attribute}"
        return f"{block.address}.{attribute}"

    def rel(self, path: str | Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(path)


def resolve_regions(tf: hcl.TerraformProject, root: Path) -> list[dict[str, str]]:
    """Every place a region is pinned, most authoritative first.

    Order: a literal `region` on an un-aliased `provider "aws"` block, then a
    `var.<name>` there resolved through the variable's default, then
    terragrunt/backend/tfvars mentions. Aliased providers (`us_east_1` for
    CloudFront certificates) are listed but never chosen as primary.
    """
    found: list[dict[str, str]] = []
    aliased: list[dict[str, str]] = []
    for block in tf.of_kind("provider"):
        if not block.labels or block.labels[0] not in ("aws", "awscc"):
            continue
        raw = block.get("region")
        if raw is None:
            continue
        value = hcl.literal(raw)
        source = f"{Path(block.file).name}:{block.line} provider \"{block.labels[0]}\""
        if not isinstance(value, str):
            ref = re.fullmatch(r"var\.([A-Za-z0-9_]+)", raw.strip())
            if ref:
                default = tf.variable_default(ref.group(1))
                if isinstance(default, str):
                    value = default
                    source += f" via var.{ref.group(1)} default"
        if isinstance(value, str) and REGION_RE.fullmatch(value):
            entry = {"region": value, "source": source}
            (aliased if block.get("alias") else found).append(entry)
    for name in ("terragrunt.hcl", "terraform.tfvars", "backend.tf", "aws-targets.json", ".env.example"):
        for path in hcl.iter_files(root, (name,)):
            if path.name != name:
                continue
            for match in REGION_RE.finditer(hcl.read_text(path)):
                found.append({"region": match.group(1), "source": f"{path.name} (mention)"})
    for path in hcl.iter_files(root, (".tfvars",)):
        for match in re.finditer(r'region\s*=\s*"([^"]+)"', hcl.read_text(path)):
            if REGION_RE.fullmatch(match.group(1)):
                found.append({"region": match.group(1), "source": f"{path.name}"})
    return found + aliased


def load(path: str | Path, *, env: str | Path | None = None) -> Project:
    """The project at `path`; with `env`, its Terraform is that one environment.

    `env` is a Terraform/Terragrunt root (e.g. `infrastructure/live/hackathon`,
    relative to `path` or absolute): only its `.tf` files and the local modules
    it calls are read, while application code is still scanned from `path`, so
    code-level evidence (tracers, MCP servers) is not lost.
    """
    root = Path(path).expanduser()
    if env is None:
        tf = hcl.load_project(root)
        region_root = root if root.is_dir() else root.parent
    else:
        env_dir = Path(env).expanduser()
        env_dir = env_dir if env_dir.is_absolute() else root / env_dir
        tf = hcl.load_project(env_dir)
        region_root = env_dir
    code = codescan.scan(root)
    project = Project(root=root, tf=tf, code=code)
    project.env = Path(env) if env is not None else None
    project.regions = resolve_regions(tf, region_root)
    return project


def provider_version(project: "Project | hcl.TerraformProject", name: str = "hashicorp/aws",
                     *, root_only: bool = False) -> dict[str, Any]:
    """The provider constraint and locked version.

    With `root_only`, only the root module's own `required_providers` and its
    `.terraform.lock.hcl` count (what `init` in that directory resolves), not
    a constraint from a called module or a sibling environment's lock.
    """
    tf = project.tf if isinstance(project, Project) else project
    constraint = None
    for block in tf.of_kind("terraform"):
        if root_only and Path(block.file).resolve().parent != Path(tf.root).resolve():
            continue
        providers = block.child("required_providers")
        if providers is None:
            continue
        for key, raw in providers.attrs.items():
            source = re.search(r'source\s*=\s*"([^"]+)"', raw)
            version = re.search(r'version\s*=\s*"([^"]+)"', raw)
            if (source and source.group(1).endswith(name)) or (name.endswith("/" + key) and not source):
                constraint = (version.group(1) if version else None) or constraint
    locked = None
    if root_only:
        lock = Path(tf.root) / ".terraform.lock.hcl"
        versions = hcl.read_lock(lock) if lock.is_file() else {}
    else:
        versions = tf.lock_versions
    for provider, version in versions.items():
        if provider.endswith(name):
            locked = version
    return {"constraint": constraint, "locked": locked}
