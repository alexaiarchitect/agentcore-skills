"""The CI0xx plan policy, and its self-containment (it is vendored into CI)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agentcore_skills import plan_policy


def plan(fixtures, name):
    return json.loads((fixtures / "plans" / name).read_text())


def ids(result):
    return {f["id"] for f in result["findings"]}


def test_a_clean_plan_passes(fixtures):
    result = plan_policy.check(plan(fixtures, "plan_ok.json"))
    assert result["summary"]["errors"] == 0 and "CI006" in ids(result)


def test_stateful_deletes_admin_policies_and_open_gateways_fail(fixtures):
    result = plan_policy.check(plan(fixtures, "plan_bad.json"))
    assert {"CI001", "CI002", "CI003", "CI004"} <= ids(result)
    assert result["counts"]["replace"] == 1 and result["counts"]["delete"] == 1


def test_allow_replace_is_per_address(fixtures):
    result = plan_policy.check(plan(fixtures, "plan_bad.json"),
                               allow_replace=("module.memory.aws_bedrockagentcore_memory.this",))
    messages = [f["message"] for f in result["findings"] if f["id"] == "CI001"]
    assert len(messages) == 1 and "user_pool" in messages[0]


def test_empty_plan_and_garbage(fixtures):
    assert "CI005" in ids(plan_policy.check(plan(fixtures, "plan_empty.json")))
    with pytest.raises(plan_policy.PlanError):
        plan_policy.check(plan(fixtures, "not_a_plan.json"))


def test_the_module_has_no_relative_imports():
    tree = ast.parse(Path(plan_policy.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, "plan_policy.py is vendored; it must not import siblings"
