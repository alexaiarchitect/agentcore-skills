"""Pull IAM policy statements out of Terraform without evaluating it.

Policies arrive in three shapes: `jsonencode({ ... })` with HCL object syntax,
a heredoc or string of raw JSON, and `data "aws_iam_policy_document"` blocks.
All three are reduced to the same list of `{effect, actions, resources,
has_condition}` records, keeping only what a static least-privilege check
needs. An action or resource that is a reference rather than a literal is
kept as its raw text, so `var.table_arn` is never mistaken for `*`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import hcl

POLICY_ATTRS = ("policy", "assume_role_policy", "inline_policy")
POLICY_RESOURCES = ("aws_iam_role_policy", "aws_iam_policy", "aws_iam_role", "aws_iam_user_policy",
                    "aws_iam_group_policy")


@dataclass
class Statement:
    effect: str = "Allow"
    actions: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    has_condition: bool = False
    principal: str = ""
    origin: str = ""
    file: str = ""
    locator: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _from_json(doc) -> list[Statement]:
    out: list[Statement] = []
    statements = doc.get("Statement", []) if isinstance(doc, dict) else []
    if isinstance(statements, dict):
        statements = [statements]
    for st in statements:
        if not isinstance(st, dict):
            continue
        actions = st.get("Action", st.get("NotAction", []))
        resources = st.get("Resource", st.get("NotResource", []))
        out.append(Statement(
            effect=str(st.get("Effect", "Allow")),
            actions=[actions] if isinstance(actions, str) else [str(a) for a in actions],
            resources=[resources] if isinstance(resources, str) else [str(r) for r in resources],
            has_condition="Condition" in st,
            principal=json.dumps(st.get("Principal", "")),
        ))
    return out


def _values(segment: str, key: str) -> list[str] | None:
    """Values of `Key = "x"` or `Key = ["x", ref]` inside one HCL object."""
    match = re.search(rf"\b{key}\s*=\s*", segment)
    if not match:
        return None
    rest = segment[match.end():]
    if rest.startswith("["):
        depth = 0
        for index, char in enumerate(rest):
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    inner = rest[1:index]
                    return [hcl.string_or_ref(item) or item for item in hcl.split_top_level(inner)]
        return []
    end = len(rest)
    for index, char in enumerate(rest):
        if char in "\n,}":
            end = index
            break
    return [hcl.string_or_ref(rest[:end].strip()) or rest[:end].strip()]


def _objects(text: str) -> list[str]:
    """Top-level `{...}` objects inside the first `Statement = [ ... ]` list."""
    match = re.search(r"\bStatement\s*=\s*\[", text)
    if not match:
        single = re.search(r"\bStatement\s*=\s*\{", text)
        if not single:
            return []
        start = single.end() - 1
        end = hcl._matching_brace(text, start)
        return [text[start:end + 1]]
    i = match.end()
    objects: list[str] = []
    depth = 0
    start = None
    while i < len(text):
        char = text[i]
        if char == '"':
            i = hcl._skip_string(text, i)
            continue
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:i + 1])
                start = None
        elif char == "]" and depth == 0:
            break
        i += 1
    return objects


def statements_from_expression(raw: str, origin: str = "") -> list[Statement]:
    text = raw.strip()
    heredoc = re.match(r"<<-?([A-Za-z_]+)\s*\n(.*)\n\s*\1\s*$", text, re.S)
    if heredoc:
        text = heredoc.group(2)
    if text.startswith("{"):
        try:
            out = _from_json(json.loads(text))
            for st in out:
                st.origin = origin
            return out
        except ValueError:
            pass
    literal = hcl.literal(text)
    if isinstance(literal, str) and literal.strip().startswith("{"):
        try:
            out = _from_json(json.loads(literal))
            for st in out:
                st.origin = origin
            return out
        except ValueError:
            pass
    out = []
    for obj in _objects(text):
        effect = (_values(obj, "Effect") or ["Allow"])[0]
        actions = _values(obj, "Action") or _values(obj, "NotAction") or []
        resources = _values(obj, "Resource") or _values(obj, "NotResource") or []
        principal = obj[obj.find("Principal"):][:120] if "Principal" in obj else ""
        out.append(Statement(effect=effect, actions=actions, resources=resources,
                             has_condition=bool(re.search(r"\bCondition\s*=", obj)),
                             principal=principal, origin=origin))
    return out


def statements_from_document(block: hcl.Block) -> list[Statement]:
    out = []
    for st in block.children("statement"):
        actions = hcl.literal(st.get("actions") or "[]")
        resources = hcl.literal(st.get("resources") or "[]")
        out.append(Statement(
            effect=(st.literal("effect") or "Allow"),
            actions=actions if isinstance(actions, list) else hcl.strings_in(st.get("actions")),
            resources=resources if isinstance(resources, list) else ([st.get("resources") or ""]),
            has_condition=bool(st.children("condition")),
            origin=block.address,
        ))
    return out


def collect(tf: hcl.TerraformProject) -> list[Statement]:
    out: list[Statement] = []
    for block in tf.blocks:
        if block.kind == "resource" and block.type in POLICY_RESOURCES:
            for attr in POLICY_ATTRS:
                if attr == "assume_role_policy":
                    continue
                raw = block.get(attr)
                if raw:
                    found = statements_from_expression(raw, origin=block.address)
                    for st in found:
                        st.file, st.locator = block.file, f"line {block.line}"
                    out.extend(found)
        if block.kind == "data" and block.type == "aws_iam_policy_document":
            found = statements_from_document(block)
            for st in found:
                st.file, st.locator = block.file, f"line {block.line}"
            out.extend(found)
    return out


def hcl_rel(block: hcl.Block) -> str:
    return f"line {block.line}"


def is_wildcard_action(action: str) -> bool:
    return action == "*" or action.endswith(":*")


def is_admin(statement: Statement) -> bool:
    return statement.effect == "Allow" and "*" in statement.actions and "*" in statement.resources
