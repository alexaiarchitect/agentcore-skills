"""The data files carry provenance, and the lookups answer as documented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcore_skills import data

DATA = Path(data.__file__).resolve().parent / "data"


@pytest.mark.parametrize("path", sorted(DATA.glob("*.json")), ids=lambda p: p.name)
def test_every_data_file_names_its_source_and_date(path):
    doc = json.loads(path.read_text())
    assert doc.get("checked", "").count("-") == 2
    assert doc.get("source") or doc.get("sources")
    assert doc.get("schema", "").startswith("agentcore-skills.")


def test_eu_central_1_availability():
    for service in ("runtime", "gateway", "identity", "memory", "observability", "evaluations", "code_interpreter",
                    "browser", "policy", "runtime_instances", "gateway_semantic_search"):
        assert data.service_available(service, "eu-central-1") is True, service
    assert data.service_available("registry", "eu-central-1") is False
    assert data.service_available("web_search", "eu-central-1") is False
    assert data.service_available("web_search", "us-east-1") is True


def test_unknown_region_and_partial_regions_are_none():
    assert data.service_available("gateway", "mars-north-1") is None
    assert data.service_available("gateway", "us-gov-west-1") is None
    assert data.service_available("memory", "us-gov-west-1") is True


def test_resource_types_map_to_services():
    assert data.service_for_resource("aws_bedrockagentcore_gateway_target") == "gateway"
    assert data.service_for_resource("awscc_bedrockagentcore_payment_manager") == "payments"
    assert data.service_for_resource("aws_s3_bucket") is None


def test_quotas_used_by_the_scripts():
    assert data.quota("gateway.tool_name_chars") == 256
    assert data.quota("gateway.targets_per_gateway") == 100
    assert data.quota("memory.strategies_per_memory") == 6


def test_mcp_revisions():
    versions = data.mcp_versions()
    assert versions["gateway_inbound"][-1] == "2026-07-28"
    assert versions["no_header_default"] == "2025-03-26"
