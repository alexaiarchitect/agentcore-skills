"""Shared test fixtures.

The plugin's library is stdlib-only, so tests import it directly. Scripts are
exercised as subprocesses, the way a skill runs them, so argument parsing and
exit codes are covered too. Nothing here touches AWS or the network beyond a
local HTTP server bound to 127.0.0.1 in the verify tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Keep the plugin tree clean while testing, as the scripts do (F03).
sys.dont_write_bytecode = True

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LIB = PLUGIN_ROOT / "lib"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(LIB))


@dataclass
class ScriptRun:
    returncode: int
    stdout: str
    stderr: str

    def json(self) -> dict:
        return json.loads(self.stdout)

    def ids(self) -> set[str]:
        doc = self.json()
        findings = doc.get("findings") or (doc.get("report") or {}).get("findings") or []
        return {f["id"] for f in findings}


@pytest.fixture(scope="session")
def plugin_root() -> Path:
    return PLUGIN_ROOT


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def run_script():
    """Run a plugin script by its path relative to the plugin root."""

    def _run(relative: str, *args, cwd: Path | str | None = None, env: dict[str, str] | None = None) -> ScriptRun:
        script = PLUGIN_ROOT / relative
        assert script.is_file(), f"no such script: {script}"
        merged = {**os.environ, **(env or {})}
        proc = subprocess.run([sys.executable, str(script), *[str(a) for a in args]], capture_output=True, text=True,
                              cwd=str(cwd) if cwd else None, timeout=120, env=merged)
        return ScriptRun(proc.returncode, proc.stdout, proc.stderr)

    return _run


@pytest.fixture
def project():
    """A fixture project by name, e.g. `project("vault_like")`."""

    def _get(name: str) -> Path:
        path = FIXTURES / "projects" / name
        assert path.is_dir(), f"no such fixture project: {path}"
        return path

    return _get


@pytest.fixture
def tmp_project(tmp_path: Path):
    """A writable copy of a fixture project, for tests that generate files."""

    def _copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(FIXTURES / "projects" / name, target)
        return target

    return _copy
