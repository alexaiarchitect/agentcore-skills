"""`agentcore-review`: one planted defect, one finding."""

from __future__ import annotations

import pytest

from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

REVIEW = "skills/agentcore-review/scripts/review.py"


def test_the_good_gateway_is_clean(run_script, project):
    result = run_script(REVIEW, project("gateway_good"), "--json")
    assert result.ids() == set() and result.returncode == EXIT_OK


@pytest.mark.parametrize("finding", [
    "ACR001",  # registry is not offered in eu-central-1
    "ACR010",  # authorizer NONE
    "ACR012",  # CUSTOM_JWT with no allowed_* restriction
    "ACR013",  # discovery URL without /.well-known/openid-configuration
    "ACR020",  # * on *
    "ACR021",  # lambda:* on *
    "ACR030",  # api_key literal
    "ACR032",  # credential variable not sensitive
    "ACR040",  # no log delivery
    "ACR043",  # target Lambda not actively traced
    "ACR050",  # MCP target with no outbound credential
    "ACR051",  # Lambda target with OAuth
    "ACR052",  # plain http upstream
    "ACR054",  # DYNAMIC listing + semantic search
    "ACR071",  # unsupported MCP revision
    "ACR080",  # 400-day expiry
    "ACR090",  # old provider lock
])
def test_every_planted_defect_is_found(run_script, project, finding):
    result = run_script(REVIEW, project("gateway_bad"), "--json")
    assert finding in result.ids()
    assert result.returncode == EXIT_FINDINGS


def test_findings_cite_a_source_and_a_place(run_script, project):
    doc = run_script(REVIEW, project("gateway_bad"), "--json").json()
    for finding in doc["findings"]:
        if finding["severity"] == "error":
            assert finding.get("source", "").startswith("https://"), finding["id"]
            assert finding.get("path"), finding["id"]


def test_missing_tracing_on_the_vault_like_project(run_script, project):
    result = run_script(REVIEW, project("vault_like"), "--json")
    ids = result.ids()
    assert {"ACR043", "ACR044", "ACR045"} <= ids
    assert result.returncode == EXIT_OK, "warnings do not fail the default gate"
    assert run_script(REVIEW, project("vault_like"), "--fail-on", "warn").returncode == EXIT_FINDINGS
    worker = [f for f in result.json()["findings"] if "worker" in f["message"]]
    assert worker == [], "only the function behind POST /mcp is on the request path"


def test_region_override(run_script, project):
    ids = run_script(REVIEW, project("gateway_good"), "--region", "us-east-1", "--json").ids()
    assert "ACR001" not in ids


def test_runtime_and_toolkit_rules(run_script, project):
    assert "ACR095" in run_script(REVIEW, project("legacy_toolkit"), "--json").ids()
    assert "ACR033" in run_script(REVIEW, project("runtime_bad"), "--json").ids()


def test_bad_target(run_script, tmp_path):
    assert run_script(REVIEW, tmp_path / "nope").returncode == EXIT_USAGE
