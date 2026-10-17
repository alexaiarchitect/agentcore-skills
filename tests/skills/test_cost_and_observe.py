"""`agentcore-cost` and `agentcore-observe`."""

from __future__ import annotations

from agentcore_skills import hcl
from agentcore_skills.report import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

COST = "skills/agentcore-cost/scripts/cost_estimate.py"
BUDGET = "skills/agentcore-cost/scripts/gen_budget.py"
REPORT = "skills/agentcore-observe/scripts/trace_report.py"
TRACING = "skills/agentcore-observe/scripts/tracing_plan.py"


def test_cost_estimate_from_a_profile(run_script, fixtures):
    result = run_script(COST, fixtures / "profiles" / "vault.json", "--as-of", "2026-10-05", "--json")
    assert result.returncode == EXIT_OK
    estimate = result.json()["estimate"]
    assert estimate["total_monthly_usd"] == 67.19
    assert estimate["memory_rate_card"] == "events"
    assert {"CST002", "CST003", "CST005"} <= result.ids()
    assert all("formula" in line for line in estimate["lines"])


def test_cost_markdown_shows_formulas_and_unpriced(run_script, fixtures):
    text = run_script(COST, fixtures / "profiles" / "gateway_only.json", "--as-of", "2026-10-06").stdout
    assert "30,000.00 invocations / 1000 x $0.005" in text and "not priced here" in text


def test_cost_rejects_bad_profiles(run_script, fixtures, tmp_path):
    assert run_script(COST, fixtures / "profiles" / "bad.json").returncode == EXIT_USAGE
    assert run_script(COST, tmp_path / "none.json").returncode == EXIT_USAGE


def test_stale_pricing_is_flagged(run_script, fixtures):
    assert "CST004" in run_script(COST, fixtures / "profiles" / "gateway_only.json", "--as-of", "2027-06-01",
                                  "--json").ids()


def test_budget_module(run_script, tmp_project, fixtures):
    root = tmp_project("vault_like")
    result = run_script(BUDGET, root, "--monthly-usd", "20", "--email", "ops@example.test",
                        "--profile", fixtures / "profiles" / "vault.json", "--json")
    assert result.returncode == EXIT_OK
    main = (root / "infrastructure" / "modules" / "agentcore-budget" / "main.tf").read_text()
    blocks = hcl.parse(main)
    alarm = next(b for b in blocks if b.type == "aws_cloudwatch_metric_alarm")
    assert alarm.literal("threshold") == 300, "2000 requests x 1.2 calls / 24 h x 3 headroom"
    assert run_script(BUDGET, root, "--monthly-usd", "0").returncode == EXIT_USAGE


def test_trace_report_finds_the_budget_owner(run_script, fixtures):
    result = run_script(REPORT, fixtures / "traces" / "xray_batch.json", "--json")
    assert result.returncode == EXIT_FINDINGS
    assert {"OBS002", "OBS003", "OBS004"} <= result.ids()
    doc = result.json()
    assert doc["discovered"]["over_budget_owners"][0]["name"] == "DynamoDB [aws]"
    assert doc["segments"][0]["self_p95_ms"] > 400


def test_trace_report_markdown_table_and_budget(run_script, fixtures):
    result = run_script(REPORT, fixtures / "traces" / "xray_batch.json", "--budget-ms", "800")
    assert result.returncode == EXIT_OK
    assert "| DynamoDB [aws] | subsegment | 30 |" in result.stdout


def test_trace_report_other_formats(run_script, fixtures):
    spans = run_script(REPORT, fixtures / "traces" / "otel_spans.jsonl", "--json")
    assert spans.json()["discovered"]["format"] == "otel-spans-jsonl"
    shallow = run_script(REPORT, fixtures / "traces" / "xray_shallow.json", "--json")
    assert {"OBS005", "OBS006"} <= shallow.ids()
    assert run_script(REPORT, fixtures / "traces" / "not_traces.json").returncode == EXIT_USAGE


def test_tracing_plan_targets_only_the_request_path(run_script, tmp_project):
    root = tmp_project("vault_like")
    result = run_script(TRACING, root, "--json")
    assert result.returncode == EXIT_OK
    assert {"OBS010", "OBS012", "OBS013"} <= result.ids()
    out = root / "infrastructure" / "modules" / "agentcore-observability"
    patch = (out / "lambda-tracing.patch.tf.txt").read_text()
    assert "aws_lambda_function.mcp" in patch and "worker" not in patch
    assert "update-trace-segment-destination" in (out / "transaction-search.sh").read_text()
    blocks = hcl.parse((out / "main.tf").read_text())
    assert {b.literal("log_type") for b in blocks if b.type == "aws_cloudwatch_log_delivery_source"} == \
        {"APPLICATION_LOGS", "TRACES"}


def test_tracing_plan_dry_run(run_script, tmp_project):
    root = tmp_project("gateway_good")
    doc = run_script(TRACING, root, "--dry-run", "--json").json()
    assert doc["dry_run"] and not (root / "terraform").exists()
    assert "OBS014" not in {f["id"] for f in doc["report"]["findings"]}
