"""`agentcore-runtime` and `agentcore-memory`."""

from __future__ import annotations

from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

CHECK = "skills/agentcore-runtime/scripts/runtime_check.py"
GEN = "skills/agentcore-runtime/scripts/gen_dockerfile.py"
MEMORY = "skills/agentcore-memory/scripts/memory_plan.py"


def test_a_contract_correct_agent_passes(run_script, project):
    result = run_script(CHECK, project("strands_agent"), "--json")
    assert result.returncode == EXIT_OK and result.ids() == {"RTM010"}
    assert result.json()["discovered"]["protocol"] == "HTTP"


def test_every_runtime_defect_is_found(run_script, project):
    result = run_script(CHECK, project("runtime_bad"), "--json")
    assert {"RTM001", "RTM002", "RTM006", "RTM007", "RTM008", "RTM009", "RTM011"} <= result.ids()
    assert result.json()["discovered"]["protocol"] == "MCP"
    assert result.returncode == EXIT_FINDINGS


def test_missing_ping_is_found(run_script, tmp_project):
    root = tmp_project("strands_agent")
    text = (root / "agent.py").read_text().replace("BedrockAgentCoreApp", "Flask").replace("@app.entrypoint", "")
    (root / "agent.py").write_text(text)
    assert {"RTM003", "RTM004"} <= run_script(CHECK, root, "--protocol", "HTTP", "--json").ids()


def test_generated_dockerfile_passes_the_check(run_script, tmp_project):
    root = tmp_project("runtime_bad")
    (root / "Dockerfile").unlink()
    (root / ".env").write_text("X=1\n")
    assert run_script(GEN, root, "--protocol", "MCP", "--entry", "server.py").returncode == EXIT_OK
    docker = (root / "Dockerfile").read_text()
    assert "--platform=linux/arm64" in docker and "EXPOSE 8000" in docker and ".env" not in docker
    ids = run_script(CHECK, root, "--json").ids()
    assert not {"RTM001", "RTM002", "RTM007", "RTM008", "RTM009"} & ids


def test_generator_dry_run_and_usage(run_script, tmp_path):
    doc = run_script(GEN, tmp_path, "--dry-run", "--json").json()
    assert doc["dry_run"] and not (tmp_path / "Dockerfile").exists()
    assert run_script(CHECK, tmp_path).returncode == EXIT_USAGE


def test_memory_plan_writes_a_module(run_script, tmp_project):
    root = tmp_project("strands_agent")
    result = run_script(MEMORY, root, "--strategies", "SEMANTIC,SUMMARIZATION", "--pii", "--json")
    assert result.returncode == EXIT_OK and "MEM006" in result.ids()
    main = (root / "terraform" / "modules" / "agentcore-memory" / "main.tf").read_text()
    assert "aws_kms_key" in main and "facts/{actorId}" in main


def test_memory_plan_refuses_bad_settings(run_script, tmp_project):
    root = tmp_project("strands_agent")
    bad = run_script(MEMORY, root, "--expiry-days", "400", "--strategies", "SEMANTIC,SEMANTIC,CUSTOM", "--json")
    assert {"MEM001", "MEM002", "MEM003"} <= bad.ids()
    assert bad.returncode == EXIT_FINDINGS
    assert not (root / "terraform").exists(), "nothing is written when the settings are wrong"
    assert "MEM005" in run_script(MEMORY, root, "--pii", "--no-kms", "--dry-run", "--json").ids()
    assert "MEM007" in run_script(MEMORY, root, "--strategies", "USER_PREFERENCE", "--dry-run", "--json").ids()
