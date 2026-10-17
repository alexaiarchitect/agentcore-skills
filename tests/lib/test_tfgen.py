"""Generated Terraform parses back, and passes the plugin's own review."""

from __future__ import annotations

import pytest

from agentcore_skills import hcl, tfgen


@pytest.mark.parametrize("upstream,outbound", [("mcp", "oauth"), ("lambda", "iam"), ("openapi", "api_key"), ("mcp", "iam")])
def test_gateway_modules_parse(upstream, outbound):
    files = tfgen.gateway_module(name="vault", upstream=upstream, checked="2026-10-05", outbound=outbound)
    blocks = hcl.parse(files["main.tf"])
    gateway = next(b for b in blocks if b.type == "aws_bedrockagentcore_gateway")
    assert gateway.literal("authorizer_type") == "CUSTOM_JWT"
    assert gateway.find("authorizer_configuration", "custom_jwt_authorizer").has("allowed_clients")
    target = next(b for b in blocks if b.type == "aws_bedrockagentcore_gateway_target")
    assert target.find("target_configuration", "mcp") is not None
    if upstream == "lambda":
        assert target.find("credential_provider_configuration", "gateway_iam_role") is not None
    hcl.parse(files["variables.tf"])


def test_semantic_search_adds_the_sync_permission():
    files = tfgen.gateway_module(name="g", upstream="mcp", checked="d", semantic=True)
    assert "SynchronizeGatewayTargets" in files["main.tf"] and 'search_type        = "SEMANTIC"' in files["main.tf"]


@pytest.mark.parametrize("recipe", ["cognito-inbound", "cognito-m2m-outbound", "api-key-outbound", "workload-identity"])
def test_identity_recipes_parse_and_keep_secrets_write_only(recipe):
    files = tfgen.identity_module(recipe=recipe, name="vault", checked="d", pool_ref=None, resource_server=None, scopes=[])
    hcl.parse(files["main.tf"])
    assert "client_secret " not in files["main.tf"] and "api_key " not in files["main.tf"]
    with pytest.raises(ValueError):
        tfgen.identity_module(recipe="nope", name="v", checked="d", pool_ref=None, resource_server=None, scopes=[])


def test_memory_and_runtime_and_budget_modules_parse():
    memory = hcl.parse(tfgen.memory_module(name="m", checked="d", expiry_days=30,
                                           strategies=["SEMANTIC", "USER_PREFERENCE"], kms=True)["main.tf"])
    assert sum(1 for b in memory if b.type == "aws_bedrockagentcore_memory_strategy") == 2
    runtime = hcl.parse(tfgen.runtime_module(name="r", protocol="MCP", checked="d", jwt=True)["main.tf"])
    rt = next(b for b in runtime if b.type == "aws_bedrockagentcore_agent_runtime")
    assert rt.find("protocol_configuration").literal("server_protocol") == "MCP"
    budget = hcl.parse(tfgen.budget_module(name="b", monthly_usd=20, emails=[], checked="d",
                                           gateway_invocations_alarm=100)["main.tf"])
    assert {b.type for b in budget} >= {"aws_budgets_budget", "aws_cloudwatch_metric_alarm"}


def test_lambda_tracing_patch_names_the_layer_and_wrapper():
    patch = tfgen.lambda_tracing_patch("aws_lambda_function.mcp", "eu-central-1")
    assert "AWSOpenTelemetryDistroJs:28" in patch and "/opt/otel-instrument" in patch
