"""`agentcore-gateway`: target decision, Cognito wiring, revisions, tool names."""

from __future__ import annotations

from agentcore_skills import hcl
from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

PLAN = "skills/agentcore-gateway/scripts/gateway_plan.py"
NAMES = "skills/agentcore-gateway/scripts/tool_names.py"


def test_an_mcp_backend_gets_an_mcp_server_target(run_script, tmp_project):
    root = tmp_project("vault_like")
    result = run_script(PLAN, root, "--dry-run", "--json")
    assert result.returncode == EXIT_OK
    doc = result.json()
    found = doc["report"]["discovered"]
    assert found["upstream"] == "mcp" and found["outbound"] == "oauth"
    assert found["endpoint"] == "https://mcp.example-vault.test/mcp"
    assert {"GWY001", "GWY002", "GWY005"} <= result.ids()
    assert "module.identity.authorized_client_ids" in doc["wiring"]
    assert "${module.identity.issuer}/.well-known/openid-configuration" in doc["wiring"]
    assert not (root / "infrastructure" / "modules" / "agentcore-gateway").exists()


def test_a_lambda_target_on_the_mcp_lambda_is_refused(run_script, tmp_project):
    root = tmp_project("vault_like")
    result = run_script(PLAN, root, "--upstream", "lambda", "--lambda-ref", "aws_lambda_function.mcp", "--dry-run", "--json")
    assert "GWY003" in result.ids() and result.returncode == EXIT_FINDINGS


def test_a_lambda_target_with_tools_writes_inline_schemas(run_script, tmp_project, fixtures):
    root = tmp_project("strands_agent")
    result = run_script(PLAN, root, "--upstream", "lambda", "--tools", fixtures / "tools" / "lambda_tools.json", "--json")
    assert result.returncode == EXIT_OK
    main = root / "terraform" / "modules" / "agentcore-gateway" / "main.tf"
    blocks = hcl.parse(main.read_text())
    target = next(b for b in blocks if b.type == "aws_bedrockagentcore_gateway_target")
    assert len(target.find("target_configuration", "mcp", "lambda", "tool_schema").children("inline_payload")) == 2


def test_with_identity_writes_both_modules(run_script, tmp_project):
    root = tmp_project("vault_like")
    run_script(PLAN, root, "--with-identity")
    modules = root / "infrastructure" / "modules"
    assert (modules / "agentcore-gateway" / "main.tf").is_file()
    assert "aws_bedrockagentcore_oauth2_credential_provider" in (modules / "agentcore-identity" / "main.tf").read_text()


def test_revisions_and_semantic_search(run_script, tmp_project):
    root = tmp_project("vault_like")
    assert "GWY007" in run_script(PLAN, root, "--versions", "2024-11-05", "--dry-run", "--json").ids()
    ids = run_script(PLAN, root, "--semantic", "--dry-run", "--json").ids()
    assert "GWY008" in ids and "GWY004" not in ids, "eu-central-1 offers semantic search"


def test_tool_names_from_json(run_script, fixtures):
    result = run_script(NAMES, fixtures / "tools" / "tools_list.json", "--target-name", "vault", "--json")
    assert {"GWY010", "GWY011", "GWY012"} <= result.ids()
    assert result.returncode == EXIT_FINDINGS


def test_tool_names_from_code(run_script, project):
    src = project("vault_like") / "apps" / "mcp-server" / "src"
    result = run_script(NAMES, "--from-code", src, "--target-name", "vault-tools", "--json")
    doc = result.json()
    assert doc["discovered"]["names"] == ["vault-tools___list_categories", "vault-tools___get_record",
                                          "vault-tools___query_records"]
    assert result.returncode == EXIT_OK
    assert "GWY013" in run_script(NAMES, "--from-code", src, "--target-name", "a___b", "--json").ids()
    assert run_script(NAMES, "--target-name", "x").returncode == EXIT_USAGE
