"""`agentcore` (router) and `agentcore-discover`."""

from __future__ import annotations

import json

from agentcore_skills.report import EXIT_OK, EXIT_USAGE

CAPS = "skills/agentcore/scripts/capabilities.py"
DISCOVER = "skills/agentcore-discover/scripts/discover.py"


def test_capabilities_list_every_skill_with_a_cost_tier(run_script):
    result = run_script(CAPS, "--json")
    assert result.returncode == EXIT_OK
    doc = result.json()
    names = {s["skill"] for s in doc["skills"]}
    assert len(names) == 13 and "agentcore-gateway" in names
    assert {s["cost"] for s in doc["skills"]} <= {"free", "aws"}
    assert next(s for s in doc["skills"] if s["skill"] == "agentcore-deploy")["cost"] == "aws"


def test_intent_routing(run_script):
    cases = {
        "put a gateway in front of my lambda": "agentcore-gateway",
        "where did the time go, my p95 is slow": "agentcore-observe",
        "how much will this cost per month": "agentcore-cost",
        "set up cognito oauth for inbound tokens": "agentcore-identity",
        "rollback the terraform apply": "agentcore-deploy",
    }
    for intent, skill in cases.items():
        assert run_script(CAPS, "--intent", intent, "--json").json()["suggestion"] == skill, intent


def test_no_intent_suggests_discovery(run_script):
    assert run_script(CAPS, "--json").json()["suggestion"] == "agentcore-discover"


def test_discover_vault_like(run_script, project):
    result = run_script(DISCOVER, project("vault_like"), "--json")
    assert result.returncode == EXIT_OK
    found = result.json()["discovered"]
    assert found["region"]["primary"] == "eu-central-1"
    assert found["application"]["mcp_backend_lambdas"] == ["aws_lambda_function.mcp"]
    assert found["terraform"]["terragrunt"] == ["infrastructure/live/production/terragrunt.hcl"]


def test_discover_markdown_has_the_four_blocks(run_script, project):
    text = run_script(DISCOVER, project("vault_like")).stdout
    for heading in ("## Found", "## Missing", "## Options", "**(recommended)**"):
        assert heading in text


def test_discover_focus_and_errors(run_script, project, tmp_path):
    doc = run_script(DISCOVER, project("strands_agent"), "--focus", "region", "--json").json()
    assert set(doc["discovered"]) == {"region", "checked"}
    assert run_script(DISCOVER, tmp_path / "missing").returncode == EXIT_USAGE
    assert run_script(DISCOVER, project("strands_agent"), "--focus", "nope").returncode == EXIT_USAGE
    empty = run_script(DISCOVER, tmp_path, "--json")
    assert "DSC001" in empty.ids() and empty.returncode == 1


def test_discover_never_writes(run_script, tmp_project):
    root = tmp_project("vault_like")
    before = sorted(p for p in root.rglob("*"))
    run_script(DISCOVER, root)
    assert sorted(p for p in root.rglob("*")) == before
    json.dumps(before, default=str)
