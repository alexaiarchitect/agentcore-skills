"""A monthly AgentCore cost estimate from a usage profile, with its arithmetic.

The estimate prices only what the published AgentCore rate card covers
(`data/pricing.json`): Gateway invocations, search and indexing; Identity
token requests; Runtime vCPU and memory seconds; Memory events, records and
retrievals; Evaluations tokens. Model tokens are priced only when the profile
supplies a per-1,000-token price, because Bedrock model prices are per model
and per region and this plugin does not pin them. Lambda, API Gateway,
CloudWatch and X-Ray are listed as **unpriced** lines so their absence from
the total is visible, not silent.

Every line carries its formula so the user can check it, and the result
says which Memory rate card applies on the `as_of` date, because short-term
Memory pricing changes on 2026-10-06 from per-1,000-events to per-GB.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from . import data

PROFILE_KEYS = {"region", "days_per_month", "gateway", "identity", "runtime", "memory",
                "evaluations", "model_tokens", "unpriced", "name", "notes"}


class ProfileError(ValueError):
    pass


def _num(section: dict, key: str, default: float = 0.0) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"`{key}` must be a number, got {value!r}")
    if value < 0:
        raise ProfileError(f"`{key}` must not be negative")
    return float(value)


def validate(profile: dict[str, Any]) -> list[str]:
    problems = []
    if not isinstance(profile, dict):
        return ["the profile must be a JSON object"]
    unknown = sorted(set(profile) - PROFILE_KEYS)
    if unknown:
        problems.append(f"unknown top-level keys: {', '.join(unknown)}")
    for key in ("gateway", "identity", "runtime", "memory", "evaluations", "model_tokens"):
        if key in profile and not isinstance(profile[key], dict):
            problems.append(f"`{key}` must be an object")
    return problems


def estimate(profile: dict[str, Any], *, as_of: date | None = None) -> dict[str, Any]:
    problems = validate(profile)
    if problems:
        raise ProfileError("; ".join(problems))
    as_of = as_of or date.today()
    prices = data.pricing()
    days = _num(profile, "days_per_month", 30.0) if "days_per_month" in profile else 30.0
    lines: list[dict[str, Any]] = []

    def line(service: str, item: str, quantity: float, unit: str, rate: float, per: float, note: str = ""):
        cost = quantity / per * rate
        lines.append({"service": service, "item": item, "quantity": round(quantity, 4), "unit": unit,
                      "rate": rate, "per": per, "monthly_usd": round(cost, 4),
                      "formula": f"{quantity:,.2f} {unit} / {per:g} x ${rate}", **({"note": note} if note else {})})

    gw = profile.get("gateway") or {}
    if gw:
        requests = _num(gw, "requests_per_day") * days
        calls = requests * _num(gw, "tool_calls_per_request", 1.0)
        lists = requests * _num(gw, "list_calls_per_request", 0.0)
        pings = _num(gw, "other_calls_per_day") * days
        line("gateway", "API invocations (tools/call, tools/list, ping)", calls + lists + pings, "invocations",
             prices["gateway"]["invocations_per_1000"], 1000)
        searches = _num(gw, "search_calls_per_day") * days
        if searches:
            line("gateway", "semantic search calls", searches, "calls", prices["gateway"]["search_per_1000"], 1000)
        tools = _num(gw, "tools_indexed")
        if tools:
            line("gateway", "tools indexed (monthly)", tools, "tools", prices["gateway"]["tools_indexed_per_100_month"], 100)

    ident = profile.get("identity") or {}
    if ident:
        tokens = _num(ident, "token_requests_per_day") * days
        if ident.get("via_runtime_or_gateway", True) and prices["identity"]["free_via_runtime_or_gateway"]:
            line("identity", "token/API-key requests via Runtime or Gateway", tokens, "requests", 0.0, 1000,
                 "no additional charge when used through Runtime or Gateway")
        else:
            line("identity", "token/API-key requests", tokens, "requests",
                 prices["identity"]["token_or_key_requests_per_1000"], 1000)

    rt = profile.get("runtime") or {}
    if rt:
        compute = str(rt.get("compute", "microvm_v2"))
        if compute not in prices["runtime"] or "vcpu_hour" not in prices["runtime"][compute]:
            raise ProfileError(f"runtime.compute must be one of microvm_v2, microvm_v2_committed, microvm_v1")
        rate = prices["runtime"][compute]
        sessions = _num(rt, "sessions_per_day") * days
        seconds = _num(rt, "avg_session_seconds", 30.0)
        active = min(1.0, _num(rt, "active_cpu_fraction", 1.0))
        vcpu = _num(rt, "vcpu", 1.0)
        gb = _num(rt, "memory_gb", 2.0)
        idle_tail = min(120.0, _num(rt, "idle_seconds_after", 0.0))
        line("runtime", f"vCPU-hours ({compute}, CPU billed only while active)",
             sessions * seconds * active * vcpu / 3600.0, "vCPU-hours", rate["vcpu_hour"], 1)
        line("runtime", f"GB-hours ({compute})", sessions * (seconds + idle_tail) * gb / 3600.0, "GB-hours",
             rate["gb_hour"], 1, "memory is reclaimed after 120 s idle")

    mem = profile.get("memory") or {}
    memory_card = "events" if as_of <= date.fromisoformat(prices["memory"]["short_term_per_1000_events"]["until"]) else "gb"
    if mem:
        events = _num(mem, "events_per_day") * days
        if memory_card == "events":
            line("memory", "short-term events (rate card until 2026-10-05)", events, "events",
                 prices["memory"]["short_term_per_1000_events"]["price"], 1000)
        else:
            gb_in = events * _num(mem, "avg_event_kb", 2.0) / (1024.0 * 1024.0)
            line("memory", "short-term ingestion (rate card from 2026-10-06)", gb_in, "GB",
                 prices["memory"]["short_term_ingest_per_gb"]["price"], 1)
            gb_out = _num(mem, "short_term_retrieved_gb_per_month")
            if gb_out:
                line("memory", "short-term retrieval", gb_out, "GB", prices["memory"]["short_term_retrieve_per_gb"]["price"], 1)
        records = _num(mem, "long_term_records")
        if records:
            custom = str(mem.get("strategy", "builtin")) in ("custom", "override", "self_managed")
            key = "long_term_records_per_1000_month_custom" if custom else "long_term_records_per_1000_month_builtin"
            line("memory", f"long-term records stored ({'custom' if custom else 'built-in'} strategy)", records,
                 "records", prices["memory"][key], 1000,
                 "custom strategies also bill model usage in your account" if custom else "")
        retrievals = _num(mem, "retrievals_per_day") * days
        if retrievals:
            line("memory", "long-term retrievals", retrievals, "retrievals", prices["memory"]["long_term_retrievals_per_1000"], 1000)

    ev = profile.get("evaluations") or {}
    if ev:
        evaluated = _num(ev, "evaluated_per_day") * days
        line("evaluations", "built-in evaluator input tokens", evaluated * _num(ev, "input_tokens_per_eval", 2000.0),
             "tokens", prices["evaluations"]["builtin_input_per_1000_tokens"], 1000)
        line("evaluations", "built-in evaluator output tokens", evaluated * _num(ev, "output_tokens_per_eval", 300.0),
             "tokens", prices["evaluations"]["builtin_output_per_1000_tokens"], 1000)

    mt = profile.get("model_tokens") or {}
    if mt:
        requests = _num(mt, "requests_per_day") * days
        if "price_per_1000_input" in mt:
            line("model", "input tokens (your price)", requests * _num(mt, "input_tokens_per_request"), "tokens",
                 _num(mt, "price_per_1000_input"), 1000)
        if "price_per_1000_output" in mt:
            line("model", "output tokens (your price)", requests * _num(mt, "output_tokens_per_request"), "tokens",
                 _num(mt, "price_per_1000_output"), 1000)

    unpriced = list(profile.get("unpriced") or ["AWS Lambda", "Amazon API Gateway", "Amazon CloudWatch Logs",
                                                  "AWS X-Ray / Transaction Search", "Amazon DynamoDB"])
    total = round(sum(l["monthly_usd"] for l in lines), 2)
    by_service: dict[str, float] = {}
    for l in lines:
        by_service[l["service"]] = round(by_service.get(l["service"], 0.0) + l["monthly_usd"], 4)
    return {
        "name": profile.get("name", "profile"),
        "region": profile.get("region"),
        "as_of": as_of.isoformat(),
        "memory_rate_card": memory_card,
        "days_per_month": days,
        "lines": lines,
        "by_service": by_service,
        "total_monthly_usd": total,
        "unpriced": unpriced,
        "pricing_source": prices["source"],
        "pricing_checked": prices["checked"],
        "region_note": prices["region_note"],
    }
