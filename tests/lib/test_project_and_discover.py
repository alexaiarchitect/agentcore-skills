"""The project model and the discovery report built on it."""

from __future__ import annotations

from agentcore_skills import project as project_mod
from agentcore_skills.discover import discover
from agentcore_skills.rules import mcp_backend_lambdas


def test_region_resolves_through_the_variable_default(project):
    model = project_mod.load(project("vault_like"))
    assert model.primary_region() == "eu-central-1"
    assert "us-east-1" in model.all_regions(), "the aliased provider is listed, not chosen"


def test_mcp_route_leads_to_the_backend_lambda(project):
    model = project_mod.load(project("vault_like"))
    assert {r["route"] for r in model.mcp_routes()} >= {"POST /mcp"}
    assert mcp_backend_lambdas(model) == {"aws_lambda_function.mcp"}


def test_references_go_through_module_outputs(project):
    model = project_mod.load(project("vault_like"))
    pool = model.cognito_pools()[0]
    assert model.module_call_for(pool) == "identity"
    assert model.ref_expr(pool) == "module.identity.user_pool_id"


def test_discovery_reports_doors_framework_and_tracing(project):
    report = discover(project("strands_agent"))
    found = report.discovered
    assert "terraform" in found["agentcore"]["doors"]
    assert "strands" in found["application"]["frameworks"]
    assert any("requires_access_token" in d for d in found["agentcore"]["identity_decorators"])
    assert found["region"]["primary"] == "us-east-1"


def test_discovery_of_the_vault_like_project_recommends_a_gateway(project):
    report = discover(project("vault_like"))
    assert report.discovered["auth"]["cognito_user_pools"] == ["aws_cognito_user_pool.users"]
    assert report.discovered["terraform"]["aws_provider_locked"] == "6.55.0"
    recommended = [o for o in report.options if o.recommended]
    assert len(recommended) == 1 and "Gateway" in recommended[0].label
    assert {g.id for g in report.gaps} == {"GAP-GATEWAY", "GAP-TRACING"}
    availability = report.discovered["region"]["availability"]["eu-central-1"]
    assert availability["gateway"] == "yes" and availability["registry"] == "no"


def test_legacy_toolkit_is_flagged(project):
    report = discover(project("legacy_toolkit"))
    assert "DSC003" in report.ids()
