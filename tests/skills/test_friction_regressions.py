"""Regression tests for the frictions logged on the first real use (0.1.0 -> 0.2.0).

Each test names the friction id from the first user's friction log.
`vault_envs` is an anonymised copy of that user's
Terraform (two Terragrunt environments, `live/production` with its lock file
and `live/hackathon` without one, and every module they call) plus the in-repo
X-Ray emitter, so these tests replay the situations that produced the
frictions.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agentcore_skills import hcl, tfgen
from agentcore_skills.report import EXIT_OK, EXIT_USAGE, GapReport

DISCOVER = "skills/agentcore-discover/scripts/discover.py"
GATEWAY = "skills/agentcore-gateway/scripts/gateway_plan.py"
NAMES = "skills/agentcore-gateway/scripts/tool_names.py"
IDENTITY = "skills/agentcore-identity/scripts/identity_plan.py"
REVIEW = "skills/agentcore-review/scripts/review.py"
DEPLOY = "skills/agentcore-deploy/scripts/deploy_plan.py"
TRACING = "skills/agentcore-observe/scripts/tracing_plan.py"


def ids(doc: dict) -> set[str]:
    findings = doc.get("findings") or (doc.get("report") or {}).get("findings") or []
    return {f["id"] for f in findings}


def findings(doc: dict, fid: str) -> list[dict]:
    return [f for f in (doc.get("findings") or (doc.get("report") or {}).get("findings") or []) if f["id"] == fid]


# -- F01: the summary agrees with the gaps it reports ---------------------------------

def test_f01_discover_summary_counts_its_gaps(run_script, project):
    doc = run_script(DISCOVER, project("vault_like"), "--json").json()
    assert doc["gaps"], "the fixture has missing pieces"
    assert doc["summary"]["gaps"] == len(doc["gaps"])
    text = run_script(DISCOVER, project("vault_like")).stdout.strip().splitlines()[-1]
    assert text.endswith(f"{len(doc['gaps'])} gap(s)._")


def test_f01_no_gap_key_without_gaps():
    assert "gaps" not in GapReport(subject=".", skill="x").summary


# -- F03: scripts leave the plugin tree clean ----------------------------------------------

def test_f03_scripts_write_no_bytecode_into_the_plugin(tmp_path, plugin_root, project):
    copy = tmp_path / "plugin"
    shutil.copytree(plugin_root, copy, ignore=shutil.ignore_patterns("tests", "__pycache__", ".pytest_cache"))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    for script, args in ((REVIEW, [project("vault_like")]), (DISCOVER, [project("vault_like")])):
        subprocess.run([sys.executable, str(copy / script), *map(str, args)], capture_output=True, env=env,
                       timeout=120, check=False)
    assert list(copy.rglob("__pycache__")) == []


# -- F13: --out-dir keeps every module ---------------------------------------------------

def test_f13_out_dir_writes_gateway_and_identity_side_by_side(run_script, tmp_project, tmp_path):
    root = tmp_project("vault_like")
    out = tmp_path / "mods"
    result = run_script(GATEWAY, root, "--with-identity", "--out-dir", out, "--json")
    assert result.returncode == EXIT_OK, result.stderr
    assert sorted(p.name for p in (out / "agentcore-gateway").iterdir()) == \
        ["main.tf", "outputs.tf", "variables.tf", "versions.tf"]
    assert sorted(p.name for p in (out / "agentcore-identity").iterdir()) == \
        ["main.tf", "outputs.tf", "variables.tf", "versions.tf"]
    assert not (tmp_path / "agentcore-identity").exists()
    dry = run_script(GATEWAY, root, "--with-identity", "--out-dir", tmp_path / "dry", "--dry-run", "--json").json()
    planned = {Path(i["path"]).parent.name for i in dry["plan"]["items"]}
    assert planned == {"agentcore-gateway", "agentcore-identity"}


def test_f13_with_identity_that_cannot_apply_says_so(run_script, tmp_project):
    doc = run_script(GATEWAY, tmp_project("vault_like"), "--with-identity", "--outbound", "api_key", "--dry-run",
                     "--json").json()
    assert "GWY015" in ids(doc)
    assert not any("agentcore-identity" in i["path"] for i in doc["plan"]["items"])


# -- F14: unique observability names -------------------------------------------------------

def test_f14_delivery_and_log_group_names_carry_the_prefix(run_script, tmp_project):
    doc = run_script(TRACING, tmp_project("gateway_good"), "--name", "env-a", "--dry-run", "--json").json()
    assert doc["plan"]["items"]
    module = tfgen.observability_module(checked="x", targets=[("gw", "var.gw_arn", "gateway-this")], name="env-a")
    main = module["main.tf"]
    names = re.findall(r'^\s*name\s*=\s*"([^"]+)"', main, re.M)
    assert names and all(n.startswith("${var.name}") or n.startswith("/aws/vendedlogs/bedrock-agentcore/${var.name}/")
                         for n in names)
    assert 'default     = "env-a"' in module["variables.tf"]
    two = tfgen.observability_module(checked="x", targets=[("gw", "var.gw_arn", "gateway-this")], name="env-b")
    assert two["main.tf"] == main  # the difference lives in var.name, not in literals


# -- F15: the interceptor the review recommends can be generated ---------------------------

@pytest.mark.parametrize("mode", ["forward-jwt", "signed-claim"])
def test_f15_interceptor_module_and_wiring(run_script, tmp_project, tmp_path, mode):
    root = tmp_project("vault_like")
    out = tmp_path / "mods"
    result = run_script(GATEWAY, root, "--with-identity", "--interceptor", mode, "--meta-key",
                        "com.example/end-user-token", "--out-dir", out, "--json")
    assert result.returncode == EXIT_OK, result.stderr
    doc = result.json()
    gateway = (out / "agentcore-gateway" / "main.tf").read_text()
    assert 'interception_points = ["REQUEST"]' in gateway and "pass_request_headers = true" in gateway
    assert 'Sid      = "InvokeInterceptor"' in gateway and "var.interceptor_lambda_arn" in gateway
    assert 'variable "interceptor_lambda_arn"' in (out / "agentcore-gateway" / "variables.tf").read_text()
    module = out / "agentcore-gateway-interceptor"
    main = (module / "main.tf").read_text()
    for needle in ('resource "aws_lambda_function" "interceptor"', 'data "archive_file" "interceptor"',
                   "AWSLambdaBasicExecutionRole", 'mode = "Active"'):
        assert needle in main
    assert ("secretsmanager:GetSecretValue" in main) is (mode == "signed-claim")
    assert 'source  = "hashicorp/archive"' in (module / "versions.tf").read_text()
    assert (module / "src" / "index.mjs").is_file()
    assert "interceptor_lambda_arn = module.agentcore_gateway_interceptor.function_arn" in doc["wiring"]
    assert 'meta_key = "com.example/end-user-token"' in doc["wiring"]
    assert "GWY017" in ids(doc) and "GWY002" not in ids(doc)


def test_f15_an_existing_interceptor_arn_is_wired_without_a_module(run_script, tmp_project):
    arn = "arn:aws:lambda:eu-central-1:111122223333:function:my-interceptor"
    root = tmp_project("vault_like")
    doc = run_script(GATEWAY, root, "--interceptor", arn, "--dry-run", "--json").json()
    assert f'interceptor_lambda_arn = "{arn}"' in doc["wiring"]
    assert not any("agentcore-gateway-interceptor" in i["path"] for i in doc["plan"]["items"])
    bad = run_script(GATEWAY, root, "--interceptor", "something", "--dry-run", "--json")
    assert bad.returncode == EXIT_USAGE


def test_f15_without_an_interceptor_gwy002_points_at_it(run_script, tmp_project):
    doc = run_script(GATEWAY, tmp_project("vault_like"), "--dry-run", "--json").json()
    fix = findings(doc, "GWY002")[0]["fix"]
    assert "--interceptor forward-jwt" in fix


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_f15_forward_jwt_handler_moves_the_bearer_into_meta_and_drops_forgeries(tmp_path):
    handler = tmp_path / "index.mjs"
    handler.write_text(tfgen.interceptor_source("forward-jwt"))
    event = {"interceptorInputVersion": "1.0", "mcp": {"gatewayRequest": {
        "path": "/mcp", "httpMethod": "POST", "headers": {"Authorization": "Bearer aaa.bbb.ccc"},
        "body": {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "t", "_meta": {"k/user": "forged", "other": 1}}}}}}
    anonymous = {"mcp": {"gatewayRequest": {"headers": {}, "body": json.dumps(
        [{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": {"k/user": "forged"}}}])}}}
    script = (f"import('{handler.as_posix()}').then(async (m) => {{"
              f"const a = await m.handler({json.dumps(event)});"
              f"const b = await m.handler({json.dumps(anonymous)});"
              "process.stdout.write(JSON.stringify([a, b])); });")
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60,
                         env={**os.environ, "META_KEY": "k/user"}, check=True).stdout
    with_token, without = json.loads(out)
    assert with_token["interceptorOutputVersion"] == "1.0"
    meta = with_token["mcp"]["transformedGatewayRequest"]["body"]["params"]["_meta"]
    assert meta == {"k/user": "aaa.bbb.ccc", "other": 1}
    assert without["mcp"]["transformedGatewayRequest"]["body"][0]["params"]["_meta"] == {}


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_f15_signed_claim_handler_is_valid_javascript(tmp_path):
    handler = tmp_path / "index.mjs"
    handler.write_text(tfgen.interceptor_source("signed-claim"))
    subprocess.run([NODE, "--check", str(handler)], check=True, timeout=60)
    text = handler.read_text()
    assert text.index("import { createHmac }") < text.index("function bearer")


def test_f15_identity_propagation_documents_the_forward_jwt_variant(plugin_root):
    text = (plugin_root / "skills/agentcore-identity/references/identity-propagation.md").read_text()
    assert "--interceptor forward-jwt" in text and "--interceptor signed-claim" in text
    assert "re-verifies" in text and "no shared secret" in text.lower()


# -- F16: one Terragrunt environment, and the in-repo X-Ray emitter -------------------------

def test_f16_an_environment_directory_follows_its_module_sources(run_script, project):
    env = project("vault_envs") / "infrastructure" / "live" / "hackathon"
    doc = run_script(REVIEW, env, "--json").json()
    followed = doc["discovered"]["modules_followed"]
    assert any(p.endswith("modules/agentcore-gateway") for p in followed)
    assert doc["discovered"]["agentcore_resources"] >= 3
    assert not any(p.endswith("modules/compute") for p in followed)


def test_f16_env_scopes_the_review_to_one_environment(run_script, project):
    root = project("vault_envs")
    hackathon = run_script(REVIEW, root, "--env", "infrastructure/live/hackathon", "--json").json()
    production = run_script(REVIEW, root, "--root", "infrastructure/live/production", "--json").json()
    everything = run_script(REVIEW, root, "--json").json()
    # Production's HTTP API, PassThrough Lambda and missing tracer stay in production.
    assert not ids(hackathon) & {"ACR043", "ACR044", "ACR045"}
    assert {"ACR043", "ACR044", "ACR045"} <= ids(production)
    assert {"ACR043", "ACR045"} <= ids(everything)
    paths = {f.get("path", "") for f in production["findings"]}
    assert not any("compute-rest" in p or "agentcore-gateway" in p for p in paths)
    assert run_script(REVIEW, root, "--env", "nope", "--json").returncode == EXIT_USAGE


def test_f16_an_active_function_with_an_in_repo_emitter_is_instrumented(run_script, project):
    from agentcore_skills.project import load
    from agentcore_skills.rules import mcp_backend_blocks

    root = project("vault_envs")
    loaded = load(root, env="infrastructure/live/hackathon")
    assert "xray-emitter" in loaded.code.tracing
    backends = mcp_backend_blocks(loaded)
    assert [Path(b.file).parent.name for b in backends] == ["compute-rest"]
    doc = run_script(REVIEW, root, "--env", "infrastructure/live/hackathon", "--json").json()
    assert "ACR044" not in ids(doc) and "ACR043" not in ids(doc)


def test_f16_module_dirs_resolve_double_slash_sources(tmp_path):
    (tmp_path / "modules" / "x").mkdir(parents=True)
    (tmp_path / "modules" / "x" / "main.tf").write_text('resource "aws_s3_bucket" "b" {}\n')
    (tmp_path / "live" / "a").mkdir(parents=True)
    (tmp_path / "live" / "a" / "main.tf").write_text('module "x" {\n  source = "../../modules//x"\n}\n')
    tf = hcl.load_project(tmp_path / "live" / "a")
    assert [b.address for b in tf.resources()] == ["aws_s3_bucket.b"]
    assert hcl.load_project(tmp_path / "live" / "a", follow_modules=False).resources() == []


# -- F17: the chosen root's provider facts, no machine paths ---------------------------------

def test_f17_deploy_plan_reads_the_chosen_roots_versions_and_lock(run_script, project):
    root = project("vault_envs")
    hackathon = run_script(DEPLOY, root, "--root", "infrastructure/live/hackathon", "--json").json()["discovered"]
    assert hackathon["aws_provider"]["constraint"] == ">= 6.64.0, < 7.0.0"
    assert hackathon["aws_provider"]["locked"].startswith("not locked yet")
    production = run_script(DEPLOY, root, "--root", "infrastructure/live/production", "--json").json()["discovered"]
    assert production["aws_provider"] == {"constraint": "~> 6.0", "locked": "6.55.0"}
    assert set(hackathon["stages"]["core"]) == {"aws_bedrockagentcore_gateway.this"}


def test_f17_commands_name_the_plugin_by_variable(run_script, project, plugin_root):
    doc = run_script(DEPLOY, project("vault_envs"), "--root", "infrastructure/live/hackathon", "--json").json()
    found = doc["discovered"]
    text = json.dumps([found["commands"], found["after_apply"], [o["runs"] for o in doc["options"]]])
    assert str(plugin_root) not in text
    assert "$AGENTCORE_PLUGIN/skills/agentcore-ci/scripts/policy_check.py" in text
    assert doc["discovered"]["setup"][0].startswith('export AGENTCORE_PLUGIN="${CLAUDE_PLUGIN_ROOT')


# -- F18: generator and reviewer agree --------------------------------------------------------

@pytest.mark.parametrize("outbound", ["oauth", "api_key"])
def test_f18_the_generated_gateway_reviews_without_acr022(run_script, tmp_project, tmp_path, outbound):
    out = tmp_path / f"mods-{outbound}"
    assert run_script(GATEWAY, tmp_project("vault_like"), "--outbound", outbound, "--out-dir", out,
                      "--json").returncode == EXIT_OK
    main = (out / "agentcore-gateway" / "main.tf").read_text()
    assert 'Resource = ["*"]' not in main
    assert ":workload-identity-directory/*" in main and ":token-vault/*" in main
    review = run_script(REVIEW, out, "--json").json()
    assert "ACR022" not in ids(review)


# -- F19: reuse an existing Cognito client; an honest state comment -----------------------------

def test_f19_client_ref_reuses_a_client(run_script, tmp_project):
    root = tmp_project("vault_like")
    doc = run_script(IDENTITY, root, "--recipe", "cognito-m2m-outbound", "--client-ref",
                     "aws_cognito_user_pool_client.machine", "--dry-run", "--json").json()
    assert doc["report"]["discovered"]["client_ref"] == "aws_cognito_user_pool_client.machine"
    assert "client_secret = module.identity." in doc["wiring"] or "client_secret = aws_cognito" in doc["wiring"]
    files = tfgen.identity_module(recipe="cognito-m2m-outbound", name="n", checked="x", pool_ref=None,
                                  resource_server=None, scopes=[], existing_client=True)
    assert 'resource "aws_cognito_user_pool_client"' not in files["main.tf"]
    assert "client_secret_wo              = var.client_secret" in files["main.tf"]
    assert "sensitive   = true" in files["variables.tf"]
    unknown = run_script(IDENTITY, root, "--recipe", "cognito-m2m-outbound", "--client-ref",
                         "aws_cognito_user_pool_client.nope", "--dry-run", "--json")
    assert unknown.returncode == EXIT_USAGE


def test_f19_a_public_client_is_flagged(run_script, tmp_project):
    doc = run_script(IDENTITY, tmp_project("vault_like"), "--recipe", "cognito-m2m-outbound", "--client-ref",
                     "aws_cognito_user_pool_client.public", "--dry-run", "--json").json()
    assert "IDN007" in ids(doc)


def test_f19_the_state_comment_is_accurate():
    main = tfgen.identity_module(recipe="cognito-m2m-outbound", name="n", checked="x", pool_ref=None,
                                 resource_server=None, scopes=[])["main.tf"]
    assert "still stores\n# `client_secret` in Terraform state" in main
    assert "keep it out of\n# Terraform state" not in main


# -- F20: notes for the target type; the probed tool list ----------------------------------------

def test_f20_target_type_mcp_drops_the_lambda_note(run_script, fixtures):
    tools = fixtures / "tools" / "tools_list.json"
    mcp = run_script(NAMES, tools, "--target-name", "vault", "--target-type", "mcp", "--json")
    assert "GWY014" not in mcp.ids()
    lam = run_script(NAMES, tools, "--target-name", "vault", "--target-type", "lambda", "--json")
    assert "GWY014" in lam.ids()


def test_f20_a_probe_report_decides_which_tools_count(run_script, tmp_path, project):
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"discovered": {"tool_names": ["find_categories", "log_entry"]}}))
    code = project("vault_like") / "apps"
    doc = run_script(NAMES, probe, "--from-code", code, "--target-name", "vault", "--target-type", "mcp",
                     "--json").json()
    assert doc["discovered"]["tools"] == 2
    assert doc["discovered"]["counted_from"] == "probed/listed tools"


# -- review: AUTHENTICATE_ONLY ---------------------------------------------------------------------

def test_authenticate_only_is_described_as_sigv4_without_passthrough(plugin_root):
    text = (plugin_root / "skills/agentcore-gateway/references/inbound-jwt-cognito.md").read_text()
    row = next(l for l in text.splitlines() if l.startswith("| `AUTHENTICATE_ONLY`"))
    assert "SigV4" in row and "not** usable with token passthrough" in row
    assert "used with token passthrough |" not in text
    ledger = plugin_root / ".dev" / "VERIFIED-FACTS.md"
    if not ledger.is_file():
        pytest.skip("the verified-facts ledger is maintainer working notes, not shipped")
    facts = ledger.read_text()
    assert "Token passthrough requires `AUTHENTICATE_ONLY` and is supported only" not in facts
    assert "| conflict |" in facts


def test_acr014_no_longer_recommends_passthrough(tmp_path, run_script):
    (tmp_path / "main.tf").write_text('resource "aws_bedrockagentcore_gateway" "g" {\n  name = "g"\n'
                                      '  authorizer_type = "AUTHENTICATE_ONLY"\n  protocol_type = "MCP"\n}\n')
    doc = run_script(REVIEW, tmp_path, "--json").json()
    acr014 = findings(doc, "ACR014")[0]
    assert "SigV4" in acr014["message"] and "cannot be combined with token passthrough" in acr014["fix"]


def test_every_verified_fact_row_names_a_full_url(plugin_root):
    ledger = plugin_root / ".dev" / "VERIFIED-FACTS.md"
    if not ledger.is_file():
        pytest.skip("the verified-facts ledger is maintainer working notes, not shipped")
    missing = []
    for line in ledger.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) < 3:
            continue
        status = next((c for c in cells[1:] if re.fullmatch(r"V2?( \([a-z /]+\))?|V / conflict|V \(.*\)", c)), None)
        if status and not re.search(r"https?://|file://", cells[-1]):
            missing.append(line[:100])
    assert missing == []
