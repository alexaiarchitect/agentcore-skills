"""The frontmatter subset, the gap report, and the write plan."""

from __future__ import annotations

import json

import pytest

from agentcore_skills import frontmatter
from agentcore_skills.report import GapReport, Option
from agentcore_skills.templating import WritePlan


def test_folded_descriptions_and_lists():
    doc = frontmatter.parse("---\nname: x\ndescription: >-\n  one\n  two\nallowed-tools: Read, Bash(python3 *)\n"
                            "tags: [a, \"b c\"]\nitems:\n  - 1\n  - two\n---\nbody\n")
    assert doc.meta["description"] == "one two"
    assert doc.meta["tags"] == ["a", "b c"] and doc.meta["items"] == [1, "two"]
    assert doc.body == "body"


def test_bad_frontmatter_names_the_line():
    with pytest.raises(frontmatter.FrontmatterError) as err:
        frontmatter.parse("---\nname: x\n  indented: y\n---\n")
    assert err.value.line == 3


def test_report_renders_both_forms():
    report = GapReport(subject="s", skill="k")
    report.add("ACR001", "error", "region", "msg", fix="fix", source="https://example.test")
    report.add_option(Option(key="1", label="Do it", cost="aws", recommended=True))
    doc = json.loads(report.to_json())
    assert doc["schema"] == "agentcore-skills.gap-report/1" and doc["summary"]["errors"] == 1
    assert doc["options"][0]["cost"] == "aws"
    assert "cost: aws" in report.to_md()


def test_write_plan_never_clobbers(tmp_path):
    existing = tmp_path / "a.tf"
    existing.write_text("mine")
    plan = WritePlan()
    plan.add(existing, "theirs")
    plan.add(tmp_path / "b.tf", "new")
    assert [i.action for i in plan.items] == ["skip", "create"]
    plan.apply()
    assert existing.read_text() == "mine" and (tmp_path / "b.tf").read_text() == "new"
