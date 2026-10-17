"""A small frontmatter reader for `SKILL.md`, plugin-eval prompts and graders.

The plugin is stdlib-only, so it reads the `---` delimited header without a
YAML dependency. The accepted grammar is the subset these files actually use:

    key: scalar                  strings (bare or quoted), ints, true/false/null
    key: [a, "b c", 3]           inline lists
    key: >-                      a folded block scalar (SKILL.md descriptions)
      folded text that runs
      over several lines
    key:                         a block list
      - item
    # comments and blank lines

Anything else (anchors, nested mappings, tabs) raises `FrontmatterError` with
the line number, because a header this plugin cannot read is a header Claude
Code may read differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DELIMITER = "---"
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(?:\s+(.*))?$")


class FrontmatterError(ValueError):
    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(f"line {line}: {message}" if line else message)


@dataclass
class Document:
    meta: dict[str, Any]
    body: str
    has_frontmatter: bool


def split(text: str) -> tuple[list[str] | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            return lines[1:index], "\n".join(lines[index + 1:]).lstrip("\n")
    raise FrontmatterError("frontmatter opened with --- but never closed", len(lines))


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value in ("", "null", "~"):
        return None
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in _split_inline(inner)]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _split_inline(text: str) -> list[str]:
    parts: list[str] = []
    current = ""
    quote: str | None = None
    for char in text:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)
    return parts


def parse_header(lines: list[str]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        number = index + 2  # line 1 is the opening delimiter
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise FrontmatterError("tabs are not allowed for indentation", number)
        if line[0].isspace():
            raise FrontmatterError(f"unexpected indentation: {line.strip()!r}", number)
        match = _KEY.match(line)
        if not match:
            raise FrontmatterError(f"expected `key: value`, got {line.strip()!r}", number)
        key, raw = match.group(1), (match.group(2) or "").strip()
        if raw.startswith(("&", "*")):
            raise FrontmatterError("anchors and aliases are not supported", number)
        if raw in (">", ">-", "|", "|-"):
            folded = raw.startswith(">")
            block: list[str] = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][0].isspace()):
                block.append(lines[index].strip())
                index += 1
            if folded:
                text = " ".join(part for part in block if part)
            else:
                text = "\n".join(block).strip("\n")
            meta[key] = text
            continue
        if raw == "":
            items: list[Any] = []
            index += 1
            while index < len(lines) and lines[index].strip().startswith("- ") and lines[index][0].isspace():
                items.append(parse_scalar(lines[index].strip()[2:]))
                index += 1
            meta[key] = items if items else None
            continue
        meta[key] = parse_scalar(raw)
        index += 1
    return meta


def parse(text: str) -> Document:
    header, body = split(text)
    if header is None:
        return Document(meta={}, body=body, has_frontmatter=False)
    return Document(meta=parse_header(header), body=body, has_frontmatter=True)


def read(path: str) -> Document:
    with open(path, encoding="utf-8") as handle:
        return parse(handle.read())
