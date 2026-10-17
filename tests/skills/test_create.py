"""`agentcore-create`: write plans, dry runs, alternatives."""

from __future__ import annotations

import pytest

from agentcore_skills import hcl
from agentcore_skills.report import EXIT_OK, EXIT_USAGE

SCAFFOLD = "skills/agentcore-create/scripts/scaffold.py"


@pytest.mark.parametrize("component", ["runtime", "gateway", "identity", "memory"])
def test_dry_run_plans_four_files_and_writes_none(run_script, tmp_project, component):
    root = tmp_project("vault_like")
    result = run_script(SCAFFOLD, root, "--component", component, "--dry-run", "--json")
    assert result.returncode == EXIT_OK
    doc = result.json()
    assert doc["dry_run"] is True and len(doc["plan"]["will_write"]) == 4
    assert not (root / "infrastructure" / "modules" / f"agentcore-{component}").exists()


def test_writing_lands_in_the_modules_tree_and_parses(run_script, tmp_project):
    root = tmp_project("vault_like")
    run_script(SCAFFOLD, root, "--component", "memory")
    main = root / "infrastructure" / "modules" / "agentcore-memory" / "main.tf"
    blocks = hcl.parse(main.read_text())
    assert any(b.type == "aws_bedrockagentcore_memory" for b in blocks)
    again = run_script(SCAFFOLD, root, "--component", "memory", "--json").json()
    assert {i["action"] for i in again["plan"]["items"]} == {"skip"}, "no clobbering without --force"


def test_cdk_and_cli_alternatives(run_script, tmp_project):
    root = tmp_project("strands_agent")
    cdk = run_script(SCAFFOLD, root, "--component", "gateway", "--iac", "cdk", "--dry-run", "--json").json()
    assert cdk["plan"]["will_write"][0].endswith("-gateway-stack.ts")
    cli = run_script(SCAFFOLD, root, "--component", "gateway", "--iac", "cli", "--json").json()
    assert any("agentcore add gateway" in c for c in cli["commands"])
    assert not (root / "cdk").exists()


def test_without_an_infrastructure_tree_uses_terraform_modules(run_script, tmp_project):
    root = tmp_project("strands_agent")
    doc = run_script(SCAFFOLD, root, "--component", "runtime", "--dry-run", "--json").json()
    assert "/terraform/modules/agentcore-runtime/" in doc["plan"]["will_write"][0]


def test_bad_arguments(run_script, tmp_path):
    assert run_script(SCAFFOLD, tmp_path / "x", "--component", "memory").returncode == EXIT_USAGE
    assert run_script(SCAFFOLD, tmp_path, "--component", "nope").returncode == EXIT_USAGE
