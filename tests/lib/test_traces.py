"""Trace exports become per-segment wall and self times."""

from __future__ import annotations

import pytest

from agentcore_skills.stats import percentile, summarize
from agentcore_skills.traces import Node, TraceFormatError, breakdown, load


def test_self_time_subtracts_the_union_of_children():
    parent = Node("Invocation", "subsegment", "", 0.0, 1.0)
    parent.children = [Node("a", "subsegment", "", 0.1, 0.4), Node("b", "subsegment", "", 0.3, 0.6)]
    assert round(parent.self_ms, 3) == 500.0


def test_batch_get_traces_nests_the_function_under_the_service(fixtures):
    traces, fmt = load(fixtures / "traces" / "xray_batch.json")
    assert fmt == "xray-batch-get-traces" and len(traces) == 30
    root = traces[0].roots[0]
    assert root.origin == "AWS::Lambda" and root.children[0].origin == "AWS::Lambda::Function"


def test_breakdown_names_dynamodb_as_the_budget_owner(fixtures):
    traces, _ = load(fixtures / "traces" / "xray_batch.json")
    result = breakdown(traces, budget_ms=500)
    assert result["total"]["over_budget"] == 3
    assert result["over_budget_self_ms_mean"][0]["name"] == "DynamoDB [aws]"
    assert result["cold_starts"]["traces"] == 3
    assert result["segments"][0]["name"] == "DynamoDB [aws]"


def test_otel_spans_and_summaries_are_read(fixtures):
    spans, fmt = load(fixtures / "traces" / "otel_spans.jsonl")
    assert fmt == "otel-spans-jsonl" and len(spans) == 30
    summaries, fmt = load(fixtures / "traces" / "xray_summaries.json")
    assert fmt == "xray-get-trace-summaries"
    assert breakdown(summaries, budget_ms=500)["total"]["count"] == 30


def test_not_a_trace_file_is_refused(fixtures):
    with pytest.raises(TraceFormatError):
        load(fixtures / "traces" / "not_traces.json")


def test_percentiles_are_nearest_rank():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50 and percentile(values, 95) == 95
    assert percentile([], 95) is None
    small = summarize([10, 20, 30], budget_ms=25)
    assert small["over_budget"] == 1 and "note" in small
