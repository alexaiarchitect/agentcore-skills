"""The plugin's own eval cases are well-formed and their scaffolds work."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from agentcore_skills import frontmatter

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
EVALS = PLUGIN_ROOT / "plugin-evals"
CASES = sorted(p for p in EVALS.iterdir() if p.is_dir() and p.name != "results")
REQUIRED = {"routing-ambiguous", "discover-reports-before-advising", "gateway-in-front-of-lambda-dry-run",
            "identity-cognito-recipe", "review-finds-missing-tracing", "observe-trace-report",
            "cost-estimate-from-profile", "deploy-never-runs-unconfirmed"}
GRADER_TYPES = {"llm", "tool_used", "regex", "tool_order", "file_exists"}


def test_the_required_cases_exist():
    assert REQUIRED <= {c.name for c in CASES}
    assert len(CASES) >= 8


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_case_layout(case):
    yaml = (case / "case.yaml").read_text()
    assert f"name: {case.name}" in yaml and "scaffold_script: scaffold.sh" in yaml
    prompt = frontmatter.read(str(case / "prompt.md"))
    assert prompt.body.strip(), "empty prompt"
    tools = prompt.meta["allowed_tools"]
    assert "Bash(python3 *)" in tools
    assert not any(t.startswith("Bash(") and t != "Bash(python3 *)" for t in tools), "Bash stays python3-only"
    graders = sorted((case / "graders").glob("*.md"))
    assert graders and (case / "graders" / "skill-fired.md").is_file()
    for grader in graders:
        meta = frontmatter.read(str(grader)).meta
        assert meta["type"] in GRADER_TYPES, grader.name
        if meta["type"] == "regex":
            re.compile(meta["pattern"])
            assert meta.get("target") in ("trace", "last_message")
    assert os.access(case / "scaffold.sh", os.X_OK)


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_scaffold_runs(case, tmp_path):
    result = subprocess.run(["bash", str(case / "scaffold.sh")], cwd=tmp_path, capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".scaffold" / "manifest.txt").is_file()


def test_the_readme_lists_every_case():
    readme = (EVALS / "README.md").read_text()
    for case in CASES:
        assert f"`{case.name}`" in readme, case.name
