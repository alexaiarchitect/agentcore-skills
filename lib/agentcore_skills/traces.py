"""Turn exported traces into "where did the time go" numbers.

Three export shapes are read, all produced by commands the user runs:

* `aws xray batch-get-traces --trace-ids ...` — `{"Traces": [{"Id", "Duration",
  "Segments": [{"Id", "Document": "<segment JSON as a string>"}]}]}`. Full
  segment trees: Lambda's `Initialization`/`Invocation`/`Overhead`,
  `DynamoDB`, `SecretsManager`, remote HTTP calls, AgentCore Gateway spans.
* `aws xray get-trace-summaries ...` — `{"TraceSummaries": [{"Id",
  "Duration", "ResponseTime", ...}]}`. Totals only, no breakdown.
* OpenTelemetry spans as JSON lines (a CloudWatch Logs export of the
  `aws/spans` log group that Transaction Search writes) — one span per line
  with `traceId`, `spanId`, `parentSpanId`, `name`, `startTimeUnixNano`,
  `endTimeUnixNano`.

For every node (segment, subsegment or span) the report keeps its wall time
and its **self time**: wall time minus the union of its children's intervals.
Self time is what answers the question — a Lambda `Invocation` of 300 ms whose
DynamoDB child took 250 ms spent 50 ms in your code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .stats import percentile, summarize


@dataclass
class Node:
    name: str
    kind: str              # segment | subsegment | span
    origin: str
    start: float           # seconds
    end: float
    children: list["Node"] = field(default_factory=list)
    error: bool = False
    fault: bool = False
    throttle: bool = False

    @property
    def duration_ms(self) -> float:
        return max(0.0, (self.end - self.start) * 1000.0)

    @property
    def self_ms(self) -> float:
        intervals = sorted((max(c.start, self.start), min(c.end, self.end)) for c in self.children
                           if c.end > self.start and c.start < self.end)
        covered = 0.0
        cur_start = cur_end = None
        for start, end in intervals:
            if cur_end is None or start > cur_end:
                if cur_end is not None:
                    covered += cur_end - cur_start
                cur_start, cur_end = start, end
            else:
                cur_end = max(cur_end, end)
        if cur_end is not None:
            covered += cur_end - cur_start
        return max(0.0, (self.end - self.start - covered) * 1000.0)

    @property
    def key(self) -> str:
        return f"{self.name} [{self.origin}]" if self.origin else self.name

    def walk(self) -> Iterable["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Trace:
    id: str
    roots: list[Node] = field(default_factory=list)
    duration_ms: float | None = None
    response_ms: float | None = None

    def total_ms(self) -> float | None:
        if self.duration_ms is not None:
            return self.duration_ms
        nodes = [n for r in self.roots for n in r.walk()]
        if not nodes:
            return None
        return (max(n.end for n in nodes) - min(n.start for n in nodes)) * 1000.0

    def nodes(self) -> list[Node]:
        return [n for r in self.roots for n in r.walk()]


class TraceFormatError(ValueError):
    pass


# -- X-Ray ----------------------------------------------------------------------

def _xray_node(doc: dict[str, Any], kind: str) -> Node:
    origin = doc.get("origin") or doc.get("namespace") or ""
    node = Node(name=str(doc.get("name", "?")), kind=kind, origin=str(origin),
                start=float(doc.get("start_time", 0.0)),
                end=float(doc.get("end_time", doc.get("start_time", 0.0)) or doc.get("start_time", 0.0)),
                error=bool(doc.get("error")), fault=bool(doc.get("fault")),
                throttle=bool(doc.get("throttle")))
    for sub in doc.get("subsegments") or []:
        if isinstance(sub, dict):
            node.children.append(_xray_node(sub, "subsegment"))
    return node


def _from_batch(doc: dict[str, Any]) -> list[Trace]:
    traces: list[Trace] = []
    for raw in doc.get("Traces") or []:
        trace = Trace(id=str(raw.get("Id", "?")))
        if raw.get("Duration") is not None:
            trace.duration_ms = float(raw["Duration"]) * 1000.0
        segments: list[tuple[dict, Node]] = []
        for seg in raw.get("Segments") or []:
            document = seg.get("Document")
            if isinstance(document, str):
                try:
                    document = json.loads(document)
                except ValueError:
                    continue
            if not isinstance(document, dict):
                continue
            segments.append((document, _xray_node(document, "segment")))
        # Segments that name a parent subsegment hang under it, so self time
        # of e.g. the Lambda service segment excludes the function segment.
        by_id: dict[str, Node] = {}
        for document, node in segments:
            by_id[str(document.get("id"))] = node
            for sub_doc, sub_node in _subsegment_pairs(document, node):
                by_id[str(sub_doc.get("id"))] = sub_node
        for document, node in segments:
            parent = by_id.get(str(document.get("parent_id"))) if document.get("parent_id") else None
            if parent is not None and parent is not node:
                parent.children.append(node)
            else:
                trace.roots.append(node)
        traces.append(trace)
    return traces


def _subsegment_pairs(document: dict, node: Node):
    for sub_doc, sub_node in zip(document.get("subsegments") or [], node.children):
        if isinstance(sub_doc, dict):
            yield sub_doc, sub_node
            yield from _subsegment_pairs(sub_doc, sub_node)


def _from_summaries(doc: dict[str, Any]) -> list[Trace]:
    out = []
    for raw in doc.get("TraceSummaries") or []:
        trace = Trace(id=str(raw.get("Id", "?")))
        if raw.get("Duration") is not None:
            trace.duration_ms = float(raw["Duration"]) * 1000.0
        if raw.get("ResponseTime") is not None:
            trace.response_ms = float(raw["ResponseTime"]) * 1000.0
        out.append(trace)
    return out


# -- OpenTelemetry spans ---------------------------------------------------------

def _from_spans(spans: list[dict[str, Any]]) -> list[Trace]:
    nodes: dict[str, tuple[dict, Node]] = {}
    for span in spans:
        start = span.get("startTimeUnixNano")
        end = span.get("endTimeUnixNano")
        if start is None:
            continue
        start_s = int(start) / 1e9
        end_s = int(end) / 1e9 if end is not None else start_s + int(span.get("durationNano", 0)) / 1e9
        attrs = span.get("attributes") or {}
        origin = attrs.get("aws.remote.service") or attrs.get("rpc.service") or \
            (span.get("resource", {}) or {}).get("attributes", {}).get("service.name", "") or span.get("kind", "")
        node = Node(name=str(span.get("name", "?")), kind="span", origin=str(origin), start=start_s, end=end_s,
                    error=str((span.get("status") or {}).get("code", "")).upper() in ("ERROR", "2"))
        nodes[str(span.get("spanId"))] = (span, node)
    traces: dict[str, Trace] = {}
    for span_id, (span, node) in nodes.items():
        trace = traces.setdefault(str(span.get("traceId")), Trace(id=str(span.get("traceId"))))
        parent = nodes.get(str(span.get("parentSpanId"))) if span.get("parentSpanId") else None
        if parent is not None:
            parent[1].children.append(node)
        else:
            trace.roots.append(node)
    return list(traces.values())


def load(path: str | Path) -> tuple[list[Trace], str]:
    """Read an export file; returns (traces, format)."""
    text = Path(path).read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        raise TraceFormatError("the file is empty")
    try:
        doc = json.loads(stripped)
    except ValueError:
        doc = None
    if isinstance(doc, dict) and "Traces" in doc:
        return _from_batch(doc), "xray-batch-get-traces"
    if isinstance(doc, dict) and "TraceSummaries" in doc:
        return _from_summaries(doc), "xray-get-trace-summaries"
    if isinstance(doc, list) and doc and isinstance(doc[0], dict) and "traceId" in doc[0]:
        return _from_spans(doc), "otel-spans"
    spans = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            raise TraceFormatError("not X-Ray JSON, a span array, or JSON lines of spans") from None
        if isinstance(item, dict) and "message" in item and isinstance(item["message"], str):
            try:
                item = json.loads(item["message"])
            except ValueError:
                continue
        if isinstance(item, dict) and "traceId" in item:
            spans.append(item)
    if spans:
        return _from_spans(spans), "otel-spans-jsonl"
    raise TraceFormatError("no traces found: expected batch-get-traces, get-trace-summaries or OTel spans")


# -- the breakdown ----------------------------------------------------------------

COLD_START_NAMES = ("Initialization", "Init", "cold_start")


def breakdown(traces: list[Trace], *, budget_ms: float) -> dict[str, Any]:
    totals = [t.total_ms() for t in traces if t.total_ms() is not None]
    per_key_wall: dict[str, list[float]] = {}
    per_key_self: dict[str, list[float]] = {}
    per_key_kind: dict[str, str] = {}
    cold = []
    errors = 0
    shallow = 0
    over_budget_contrib: dict[str, list[float]] = {}
    for trace in traces:
        nodes = trace.nodes()
        if not nodes:
            continue
        if len(nodes) <= 2 and all(not n.children for n in nodes):
            shallow += 1
        wall: dict[str, float] = {}
        self_: dict[str, float] = {}
        for node in nodes:
            wall[node.key] = wall.get(node.key, 0.0) + node.duration_ms
            self_[node.key] = self_.get(node.key, 0.0) + node.self_ms
            per_key_kind.setdefault(node.key, node.kind)
            if node.error or node.fault:
                errors += 1
        for key, value in wall.items():
            per_key_wall.setdefault(key, []).append(value)
        for key, value in self_.items():
            per_key_self.setdefault(key, []).append(value)
        cold_nodes = [n for n in nodes if n.name in COLD_START_NAMES]
        if cold_nodes:
            cold.append(sum(n.duration_ms for n in cold_nodes))
        total = trace.total_ms()
        if total is not None and total > budget_ms:
            for key, value in self_.items():
                over_budget_contrib.setdefault(key, []).append(value)
    rows = []
    for key in per_key_wall:
        rows.append({
            "name": key,
            "kind": per_key_kind.get(key, ""),
            "traces": len(per_key_wall[key]),
            "wall_p50_ms": round(percentile(per_key_wall[key], 50) or 0.0, 2),
            "wall_p95_ms": round(percentile(per_key_wall[key], 95) or 0.0, 2),
            "self_p50_ms": round(percentile(per_key_self[key], 50) or 0.0, 2),
            "self_p95_ms": round(percentile(per_key_self[key], 95) or 0.0, 2),
            "self_total_ms": round(sum(per_key_self[key]), 2),
        })
    rows.sort(key=lambda r: (-r["self_p95_ms"], r["name"]))
    worst = sorted(((k, sum(v) / len(v)) for k, v in over_budget_contrib.items()), key=lambda kv: -kv[1])
    return {
        "traces": len(traces),
        "with_segments": sum(1 for t in traces if t.nodes()),
        "total": summarize(totals, budget_ms=budget_ms),
        "segments": rows,
        "cold_starts": {"traces": len(cold), "share_pct": round(100.0 * len(cold) / len(traces), 1) if traces else 0.0,
                        **({"p95_ms": round(percentile(cold, 95), 2), "p50_ms": round(percentile(cold, 50), 2)} if cold else {})},
        "errors_or_faults": errors,
        "shallow_traces": shallow,
        "over_budget_self_ms_mean": [{"name": k, "mean_self_ms": round(v, 2)} for k, v in worst[:5]],
    }
