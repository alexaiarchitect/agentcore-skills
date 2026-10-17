"""`agentcore-identity`: recipes, Cognito facts, CLI equivalents."""

from __future__ import annotations

import pytest

from agentcore_skills.report import EXIT_OK, EXIT_USAGE

PLAN = "skills/agentcore-identity/scripts/identity_plan.py"


def test_cognito_inbound_recipe_explains_client_id(run_script, project):
    result = run_script(PLAN, project("vault_like"), "--recipe", "cognito-inbound", "--dry-run", "--json")
    assert result.returncode == EXIT_OK
    assert {"IDN002", "IDN003"} <= result.ids()
    commands = result.json()["cli_equivalent"]
    assert "cognito-idp.eu-central-1.amazonaws.com" in commands[0]


def test_m2m_outbound_warns_about_identity_and_uses_write_only_secrets(run_script, tmp_project):
    root = tmp_project("vault_like")
    result = run_script(PLAN, root, "--recipe", "cognito-m2m-outbound", "--scopes", "records.read", "--json")
    assert {"IDN004", "IDN006"} <= result.ids()
    main = (root / "infrastructure" / "modules" / "agentcore-identity" / "main.tf").read_text()
    assert "client_secret_wo" in main and "CustomOauth2" in main
    assert '"https://mcp.example-vault.test/mcp/records.read"' in main
    assert any("create-oauth2-credential-provider" in c for c in result.json()["cli_equivalent"])


@pytest.mark.parametrize("recipe", ["api-key-outbound", "workload-identity"])
def test_other_recipes(run_script, project, recipe):
    result = run_script(PLAN, project("strands_agent"), "--recipe", recipe, "--dry-run", "--json")
    assert result.returncode == EXIT_OK and len(result.json()["plan"]["will_write"]) == 4


def test_no_pool_is_reported(run_script, project):
    assert "IDN001" in run_script(PLAN, project("strands_agent"), "--recipe", "cognito-inbound", "--dry-run",
                                  "--json").ids()
    assert run_script(PLAN, project("strands_agent"), "--recipe", "nope").returncode == EXIT_USAGE
