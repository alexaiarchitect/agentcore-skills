"""Conventions that hold across the whole plugin.

These are the rules that stop the plugin drifting as it grows: every skill has
a usable description and a completion checklist, every reference cites its
sources, every script supports `--json` and explains itself in `--help`,
every linked file exists, every script path a skill prints resolves —
including the cross-skill ones — no bare `SKILL_DIR` placeholder survives,
writers support `--dry-run`, the plugin-side code never imports an AWS SDK or
anything outside the standard library, the code never shells out to
terraform or aws, and the data files carry their provenance.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(p for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir())
SKILL_FILES = [p / "SKILL.md" for p in SKILLS]
REFERENCES = sorted((PLUGIN_ROOT / "skills").rglob("references/*.md"))
SCRIPTS = sorted(p for p in (PLUGIN_ROOT / "skills").rglob("scripts/*.py") if not p.name.startswith("_"))
LIB_MODULES = sorted((PLUGIN_ROOT / "lib" / "agentcore_skills").glob("*.py"))

EXPECTED_SKILLS = {
    "agentcore", "agentcore-discover", "agentcore-create", "agentcore-review", "agentcore-gateway",
    "agentcore-identity", "agentcore-runtime", "agentcore-memory", "agentcore-deploy", "agentcore-verify",
    "agentcore-observe", "agentcore-cost", "agentcore-ci",
}

#: Scripts that write files must offer a dry run. deploy_plan.py only prints,
#: and accepts --dry-run for symmetry.
WRITERS = {"scaffold.py", "gateway_plan.py", "identity_plan.py", "gen_dockerfile.py", "memory_plan.py",
           "tracing_plan.py", "gen_budget.py", "gen_ci.py", "deploy_plan.py", "verify.py"}


def frontmatter(path: Path) -> dict:
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))
    from agentcore_skills import frontmatter as fm

    return fm.read(str(path)).meta


# -- structure -------------------------------------------------------------

def test_the_expected_skills_are_all_present():
    assert {p.name for p in SKILLS} == EXPECTED_SKILLS


def test_the_plugin_manifest_is_valid():
    manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "agentcore"
    assert manifest["description"]
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"])
    assert manifest["license"] == "Apache-2.0"
    assert manifest["repository"] == "https://github.com/alexaiarchitect/agentcore-skills"
    assert "dependencies" not in manifest, "aws-agents is a soft reference, not a dependency"
    assert manifest["experimental"]["evals"] == "plugin-evals"


def test_the_marketplace_manifest_names_this_plugin():
    marketplace = json.loads((PLUGIN_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert marketplace["name"] == "alexaiarchitect-agentcore"
    assert [p["name"] for p in marketplace["plugins"]] == ["agentcore"]


def test_licensing_files_are_present():
    license_text = (PLUGIN_ROOT / "LICENSE").read_text()
    assert "Apache License" in license_text and "Copyright 2026 Alex" in license_text
    notices = (PLUGIN_ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    for name in ("terraform-provider-aws", "agent-toolkit-for-aws", "sample-strands-agent-with-agentcore",
                 "docs.aws.amazon.com/bedrock-agentcore"):
        assert name in notices


def test_the_readme_states_what_it_was_checked_against():
    readme = (PLUGIN_ROOT / "README.md").read_text()
    assert "2026-10-05" in readme and "/plugin install agentcore@alexaiarchitect-agentcore" in readme
    for skill in EXPECTED_SKILLS:
        assert f"/agentcore:{skill}" in readme, skill


# -- SKILL.md --------------------------------------------------------------

@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_has_a_name_matching_its_directory(skill):
    assert frontmatter(skill)["name"] == skill.parent.name


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_description_says_when_to_use_and_when_not_to(skill):
    description = frontmatter(skill)["description"]
    assert len(description) > 200, "too short to route on"
    assert "Use when" in description
    assert "Don't use" in description, "a description needs to say what it is not for"
    assert len(description) <= 2000


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_declares_the_tools_it_needs(skill):
    meta = frontmatter(skill)
    tools = meta["allowed-tools"]
    assert "AskUserQuestion" in tools, "the confirm step needs it"
    assert "Bash(python3 *)" in tools, "every skill runs its own scripts"
    for forbidden in ("Bash(terraform", "Bash(terragrunt", "Bash(aws ", "Bash(cdk", "Bash(agentcore", "Bash(*)"):
        assert forbidden not in tools, f"{skill.parent.name} must not run {forbidden}"
    assert meta.get("argument-hint")


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_no_skill_forks_its_context(skill):
    """A forked context cannot ask the user anything, and every skill here
    confirms before acting."""
    assert "context" not in frontmatter(skill)


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_bodies_stay_short_enough_to_load(skill):
    lines = skill.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200, f"{len(lines)} lines; move detail into references/"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_follows_the_protocol(skill):
    text = skill.read_text(encoding="utf-8")
    assert "## Completion checklist" in text
    assert "## Flow" in text
    assert "AskUserQuestion" in text.split("## Flow", 1)[1], "the flow must confirm before acting"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_linked_reference_exists(skill):
    text = skill.read_text(encoding="utf-8")
    for link in re.findall(r"\]\(((?:\.\./[a-z-]+/)?references/[^)]+)\)", text):
        assert (skill.parent / link).resolve().is_file(), f"{skill.parent.name}: dead link to {link}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_reference_file_is_linked_from_its_skill(skill):
    text = skill.read_text(encoding="utf-8")
    for reference in sorted((skill.parent / "references").glob("*.md")):
        assert f"references/{reference.name}" in text, f"{skill.parent.name}: {reference.name} is never linked"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_script_a_skill_names_exists(skill):
    text = skill.read_text(encoding="utf-8")
    for match in re.findall(r"(?:\$\{CLAUDE_SKILL_DIR\}/|`)(scripts/[a-z_]+\.py)", text):
        assert (skill.parent / match).is_file(), f"{skill.parent.name}: names a missing {match}"


CROSS_SKILL_SCRIPT = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/\.\./([a-z-]+)/(scripts/[a-z_]+\.py)")


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_cross_skill_script_a_skill_names_exists(skill):
    text = skill.read_text(encoding="utf-8")
    for other, script in CROSS_SKILL_SCRIPT.findall(text):
        assert (skill.parent.parent / other / script).is_file(), f"{skill.parent.name}: names a missing {other}/{script}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_script_in_a_skill_is_documented_by_it(skill):
    text = skill.read_text(encoding="utf-8")
    for script in sorted((skill.parent / "scripts").glob("*.py")):
        assert f"scripts/{script.name}" in text, f"{skill.parent.name}: {script.name} is undocumented"


COMMAND_BEARING = SKILL_FILES + REFERENCES
BARE_SKILL_DIR = re.compile(r"(?<!\{CLAUDE_)\bSKILL_DIR\b")


@pytest.mark.parametrize("document", COMMAND_BEARING, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_no_bare_skill_dir_placeholder_survives(document):
    text = document.read_text(encoding="utf-8")
    offenders = [line.strip() for line in text.splitlines() if BARE_SKILL_DIR.search(line)]
    assert offenders == [], f"use ${{CLAUDE_SKILL_DIR}}: {offenders}"


# -- references ------------------------------------------------------------

@pytest.mark.parametrize("reference", REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_reference_cites_its_sources(reference):
    text = reference.read_text(encoding="utf-8")
    assert "Sources:" in text, "add a Sources: footer"
    assert text.rstrip().endswith((".", ")", "`")), "the footer looks truncated"
    footer = text.split("Sources:", 1)[1]
    assert "https://" in footer or "this plugin" in footer


@pytest.mark.parametrize("reference", REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_references_are_substantial_but_not_sprawling(reference):
    lines = reference.read_text(encoding="utf-8").splitlines()
    assert 25 <= len(lines) <= 250, f"{len(lines)} lines"


@pytest.mark.parametrize("reference", REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_references_cite_the_current_docs_hosts(reference):
    text = reference.read_text(encoding="utf-8")
    assert "docs.aws.amazon.com/bedrock-agentcore/latest/devguide" in text or "aws.amazon.com" in text \
        or "registry.terraform.io" in text or "github.com" in text or "developer.hashicorp.com" in text


# -- scripts ---------------------------------------------------------------

def help_of(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_has_help_and_a_docstring(script):
    result = help_of(script)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) > 200, "the help text should explain why, not just how"
    assert script.read_text().split("\n", 1)[1].lstrip().startswith('"""')


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_speaks_json(script):
    assert "--json" in help_of(script).stdout


@pytest.mark.parametrize("script", [s for s in SCRIPTS if s.name in WRITERS], ids=lambda p: p.name)
def test_every_writer_has_a_dry_run(script):
    assert "--dry-run" in help_of(script).stdout


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_finds_the_shared_library_the_same_way(script):
    assert 'parents[3] / "lib"' in script.read_text(encoding="utf-8")


def code_outside_strings(path: Path) -> str:
    """The module's source with string literals and comments blanked out, so
    generated Terraform, workflow text and docstrings do not count as code."""
    import ast as _ast
    import io
    import tokenize

    source = path.read_text(encoding="utf-8")
    dropped = {tokenize.STRING, tokenize.COMMENT}
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        if hasattr(tokenize, name):
            dropped.add(getattr(tokenize, name))
    kept: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in dropped:
            continue
        kept.append(token.string)
    _ast.parse(source)
    return " ".join(kept)


BANNED = ("import boto3", "from boto3", "import botocore", "from botocore", "aiobotocore", "import requests", "import yaml", "from yaml", "import httpx",
          "import pydantic", "from pydantic", "import hcl2", "from hcl2")
#: Nothing in the plugin may execute a command; it emits them.
NO_SUBPROCESS = ("subprocess", "os . system", "os . popen", "os . exec", "pty")


@pytest.mark.parametrize("module", SCRIPTS + LIB_MODULES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_code_is_standard_library_only(module):
    code = code_outside_strings(module)
    for name in BANNED:
        assert name not in code, f"{module.name} uses {name} in real code"


@pytest.mark.parametrize("module", SCRIPTS + LIB_MODULES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_code_never_runs_commands(module):
    """terraform, terragrunt, aws, cdk and agentcore are emitted, never executed."""
    code = code_outside_strings(module)
    for name in NO_SUBPROCESS:
        assert name not in code, f"{module.name} uses {name}"


@pytest.mark.parametrize("module", LIB_MODULES, ids=lambda p: p.name)
def test_every_library_module_explains_itself(module):
    assert module.read_text(encoding="utf-8").lstrip().startswith('"""'), f"{module.name} has no module docstring"


def test_the_readers_never_execute_what_they_read():
    for name in ("hcl.py", "codescan.py", "project.py", "iam.py"):
        code = code_outside_strings(PLUGIN_ROOT / "lib" / "agentcore_skills" / name)
        for banned in ("exec (", "eval (", "importlib", "__import__"):
            assert banned not in code, f"{name} uses {banned}"
        assert not re.search(r"(?<!re \. )\bcompile \(", code), f"{name} uses the compile builtin"


def test_scripts_compile_on_python_3_10():
    """The floor is 3.10. When a 3.10 interpreter is installed, prove it."""
    import shutil

    python310 = shutil.which("python3.10")
    if not python310:
        pytest.skip("no python3.10 on PATH")
    files = [str(p) for p in SCRIPTS + LIB_MODULES]
    # -B and an in-memory compile: proving the syntax must not leave __pycache__ in the plugin (F03).
    check = "import sys\nfor f in sys.argv[1:]:\n    compile(open(f, encoding='utf-8').read(), f, 'exec')"
    result = subprocess.run([python310, "-B", "-c", check, *files], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# -- data provenance ---------------------------------------------------------

def test_data_files_name_source_and_checked_date():
    for path in sorted((PLUGIN_ROOT / "lib" / "agentcore_skills" / "data").glob("*.json")):
        doc = json.loads(path.read_text())
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", doc["checked"]), path.name
        assert doc.get("source") or doc.get("sources"), path.name


def test_the_library_dates_agree():
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))
    from agentcore_skills import DOCS_CHECKED, data

    for name in ("regions", "pricing", "quotas", "terraform_resources", "mcp_versions"):
        assert data.load(name)["checked"] == DOCS_CHECKED, name


# -- generated content never carries a secret ---------------------------------

SECRETS = re.compile(r"(AKIA[0-9A-Z]{16}|sk-ant-[A-Za-z0-9_\-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def test_no_secret_shaped_string_ships():
    offenders = []
    for path in PLUGIN_ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix not in (".md", ".py", ".json", ".tf", ".hcl", ".yml", ".yaml", ".sh", ".txt", ".jsonl", ""):
            continue
        if path.name == "test_plugin_hygiene.py":
            continue
        if SECRETS.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(PLUGIN_ROOT)))
    assert offenders == []


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_leaves_no_bytecode_behind(script):
    """A read-only install must stay clean: no __pycache__ under skills/ or lib/ (friction F03)."""
    text = script.read_text(encoding="utf-8")
    assert "sys.dont_write_bytecode = True" in text
    assert text.index("sys.dont_write_bytecode = True") < text.index('parents[3] / "lib"')
