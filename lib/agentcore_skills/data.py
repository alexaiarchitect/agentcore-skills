"""The plugin's tabular facts: regions, pricing, quotas, Terraform coverage.

Facts that change on AWS's schedule rather than this plugin's live as JSON
files beside this module, each with the URL it was read from and the date it
was checked. Scripts load them through here so a report can always say where
a number came from and how old it is; `.dev/check_sources.py` watches the same
URLs and flags when they move.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    with (DATA_DIR / f"{name}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def regions() -> dict[str, Any]:
    return load("regions")


def pricing() -> dict[str, Any]:
    return load("pricing")


def quotas() -> dict[str, Any]:
    return load("quotas")


def terraform_coverage() -> dict[str, Any]:
    return load("terraform_resources")


def mcp_versions() -> dict[str, Any]:
    return load("mcp_versions")


def quota(key: str) -> Any:
    return quotas()["quotas"][key]["value"]


def service_available(service: str, region: str) -> bool | None:
    """True/False when the table says; None when the region is unknown or partial."""
    table = regions()
    if region in table.get("partial_regions", {}):
        return True if service in table["partial_regions"][region] else None
    if region not in table["regions"]:
        return None
    if service in table["limited"]:
        return region in table["limited"][service]
    if service in table["everywhere"]:
        return True
    return None


def service_for_resource(resource_type: str) -> str | None:
    table = regions()["resource_service"]
    if resource_type in table:
        return table[resource_type]
    if resource_type.startswith("awscc_bedrockagentcore_"):
        stem = resource_type[len("awscc_bedrockagentcore_"):]
        for key in ("runtime", "gateway", "memory", "identity", "browser", "code_interpreter",
                    "evaluat", "policy", "harness", "payment", "registry"):
            if stem.startswith(key):
                return {"evaluat": "evaluations", "payment": "payments"}.get(key, key)
    return None


def age_days(checked: str, today: date | None = None) -> int:
    today = today or date.today()
    return (today - date.fromisoformat(checked)).days


def provenance(name: str) -> str:
    table = load(name)
    return f"{table.get('source') or ', '.join(table.get('sources', []))} (checked {table['checked']})"
