"""Policy checks over `terraform show -json <plan>`: the `CI0xx` band.

This module is self-contained on purpose: `agentcore-ci/scripts/gen_ci.py`
vendors a copy of it into the user's repository (`ci/agentcore_plan_policy.py`)
so the CI job needs nothing from the plugin and nothing beyond Python's
standard library. Keep it free of relative imports.

What it refuses, and why:

* `CI001` a plan that **deletes or replaces** a stateful resource — an
  AgentCore Memory (conversation history), a Cognito user pool (every user's
  identity), a credential provider (secrets in the token vault) — or a
  gateway (its URL is the endpoint every client is configured with).
* `CI002` an IAM policy in the planned values that allows `*` on `*`.
* `CI003` a gateway planned with `authorizer_type = "NONE"`.
* `CI004` a gateway planned without pinned MCP `supported_versions`.
* `CI005` (info) a plan with no changes.
* `CI006` (info) a plan that creates billable AgentCore resources, listed so a
  reviewer sees the cost surface of the change.

Exit codes: 0 clean, 1 an error-level finding, 2 the file is not a plan.
"""

from __future__ import annotations

import json
from typing import Any

STATEFUL = {
    "aws_bedrockagentcore_memory": "conversation and long-term memory records",
    "aws_bedrockagentcore_gateway": "the gateway URL every client is configured with",
    "aws_bedrockagentcore_oauth2_credential_provider": "the client secret held in the token vault",
    "aws_bedrockagentcore_api_key_credential_provider": "the API key held in the token vault",
    "aws_bedrockagentcore_workload_identity": "the identity other resources reference",
    "aws_cognito_user_pool": "every user's identity and the token issuer",
    "aws_dynamodb_table": "application data",
}
BILLABLE_PREFIX = "aws_bedrockagentcore_"


class PlanError(ValueError):
    pass


def _finding(fid: str, severity: str, message: str, address: str = "", fix: str = "") -> dict[str, Any]:
    out = {"id": fid, "severity": severity, "area": "plan-policy", "message": message}
    if address:
        out["locator"] = address
    if fix:
        out["fix"] = fix
    return out


def _policy_statements(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, dict):
        return []
    statements = value.get("Statement", [])
    return [statements] if isinstance(statements, dict) else [s for s in statements if isinstance(s, dict)]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def check(plan: dict[str, Any], *, allow_replace: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(plan, dict) or "resource_changes" not in plan and "planned_values" not in plan:
        raise PlanError("not a `terraform show -json` plan: no resource_changes or planned_values")
    findings: list[dict[str, Any]] = []
    changes = plan.get("resource_changes") or []
    counted = {"create": 0, "update": 0, "delete": 0, "replace": 0, "no-op": 0}
    billable: list[str] = []
    for change in changes:
        address = change.get("address", "?")
        rtype = change.get("type", "")
        actions = (change.get("change") or {}).get("actions") or []
        after = (change.get("change") or {}).get("after") or {}
        if actions == ["no-op"] or actions == ["read"]:
            counted["no-op"] += 1
            continue
        replace = "delete" in actions and "create" in actions
        if replace:
            counted["replace"] += 1
        elif "delete" in actions:
            counted["delete"] += 1
        elif "create" in actions:
            counted["create"] += 1
        elif "update" in actions:
            counted["update"] += 1
        if ("delete" in actions) and rtype in STATEFUL and address not in allow_replace:
            verb = "replaces" if replace else "deletes"
            findings.append(_finding("CI001", "error", f"the plan {verb} {address}: {STATEFUL[rtype]}", address,
                                     "if intended, re-run with --allow-replace " + address +
                                     " after a human has reviewed the plan; otherwise find the argument "
                                     "that forces replacement (`terraform plan` marks it) and revert it."))
        if rtype.startswith("aws_iam_") or rtype == "aws_iam_policy_document":
            for key in ("policy", "inline_policy"):
                for statement in _policy_statements(after.get(key)):
                    if statement.get("Effect", "Allow") == "Allow" and "*" in _as_list(statement.get("Action")) \
                            and "*" in _as_list(statement.get("Resource")):
                        findings.append(_finding("CI002", "error", f"{address} allows * on *", address,
                                                 "scope actions and resources."))
        if rtype == "aws_bedrockagentcore_gateway" and ("create" in actions or "update" in actions):
            if str(after.get("authorizer_type", "")).upper() == "NONE":
                findings.append(_finding("CI003", "error", f"{address} is planned with authorizer_type NONE", address,
                                         "use CUSTOM_JWT or AWS_IAM."))
            protocol = after.get("protocol_configuration") or []
            mcp = (protocol[0].get("mcp") if protocol and isinstance(protocol[0], dict) else None) or []
            versions = mcp[0].get("supported_versions") if mcp and isinstance(mcp[0], dict) else None
            if not versions:
                findings.append(_finding("CI004", "warn", f"{address} does not pin MCP supported_versions", address,
                                         "pin the revisions your clients and tests use."))
        if rtype.startswith(BILLABLE_PREFIX) and "create" in actions:
            billable.append(address)
    if not any(counted[k] for k in ("create", "update", "delete", "replace")):
        findings.append(_finding("CI005", "info", "the plan has no changes"))
    if billable:
        findings.append(_finding("CI006", "info", f"creates {len(billable)} AgentCore resource(s): {', '.join(billable)}",
                                 fix="see /agentcore:agentcore-cost for what they bill."))
    summary = {"errors": sum(1 for f in findings if f["severity"] == "error"),
               "warnings": sum(1 for f in findings if f["severity"] == "warn"),
               "infos": sum(1 for f in findings if f["severity"] == "info")}
    return {"schema": "agentcore-skills.plan-policy/1", "counts": counted, "findings": findings, "summary": summary}


def render_md(result: dict[str, Any]) -> str:
    lines = ["# agentcore plan policy", ""]
    counts = result["counts"]
    described = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    lines.append(f"Plan: {described or 'empty'}")
    lines.append("")
    for finding in result["findings"]:
        lines.append(f"- `{finding['id']}` ({finding['severity']}) {finding['message']}")
        if finding.get("fix"):
            lines.append(f"  - Fix: {finding['fix']}")
    s = result["summary"]
    lines += ["", f"_Summary: {s['errors']} error(s), {s['warnings']} warning(s), {s['infos']} note(s)._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point used by the vendored CI copy."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Check a `terraform show -json` plan against the CI0xx policy.")
    parser.add_argument("plan")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-replace", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        with open(args.plan, encoding="utf-8") as handle:
            plan = json.load(handle)
        result = check(plan, allow_replace=tuple(args.allow_replace))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render_md(result))
    return 1 if result["summary"]["errors"] else 0
