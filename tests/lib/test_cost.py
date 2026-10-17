"""The cost model: rate-card selection, formulas, and refusal of bad profiles."""

from __future__ import annotations

import json
from datetime import date

import pytest

from agentcore_skills.cost import ProfileError, estimate


def load(fixtures, name):
    return json.loads((fixtures / "profiles" / name).read_text())


def test_memory_rate_card_switches_on_2026_10_06(fixtures):
    profile = load(fixtures, "vault.json")
    before = estimate(profile, as_of=date(2026, 10, 5))
    after = estimate(profile, as_of=date(2026, 10, 6))
    assert before["memory_rate_card"] == "events" and after["memory_rate_card"] == "gb"
    assert before["by_service"]["memory"] > after["by_service"]["memory"]


def test_gateway_line_is_exact(fixtures):
    result = estimate(load(fixtures, "gateway_only.json"), as_of=date(2026, 10, 5))
    line = result["lines"][0]
    assert line["quantity"] == 30000 and line["monthly_usd"] == pytest.approx(0.15)
    assert "AWS Lambda" in result["unpriced"]


def test_identity_through_gateway_is_free(fixtures):
    result = estimate(load(fixtures, "vault.json"), as_of=date(2026, 10, 5))
    assert result["by_service"]["identity"] == 0.0


def test_runtime_bills_cpu_only_while_active(fixtures):
    profile = {"runtime": {"sessions_per_day": 100, "avg_session_seconds": 36, "active_cpu_fraction": 0.5,
                           "vcpu": 1, "memory_gb": 1}}
    result = estimate(profile, as_of=date(2026, 10, 5))
    cpu = next(l for l in result["lines"] if l["unit"] == "vCPU-hours")
    assert cpu["quantity"] == pytest.approx(100 * 30 * 36 * 0.5 / 3600)


def test_bad_profiles_are_refused(fixtures):
    with pytest.raises(ProfileError):
        estimate(load(fixtures, "bad.json"))
    with pytest.raises(ProfileError):
        estimate({"runtime": {"compute": "gpu"}})
