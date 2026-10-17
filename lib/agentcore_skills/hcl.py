"""A forgiving HCL reader: blocks, attributes and literal values, no evaluation.

Terraform is the IaC this plugin prefers, so most checks start here. This is
not a Terraform parser and never pretends to be: it finds `resource`, `data`,
`module`, `variable`, `provider`, `terraform` and `locals` blocks, their
nested blocks and their `key = expression` attributes, keeping every
expression as **raw text**. Helpers then turn the raw text into a Python value
only when it is a literal (`"x"`, `42`, `true`, `["a", "b"]`). An expression
that references something (`var.region`, `aws_iam_role.x.arn`) stays text,
and a check that needs its value says "could not resolve" instead of guessing.

It understands comments (`#`, `//`, `/* */`), quoted strings with `${...}`
interpolation (including nested quotes inside the interpolation), and heredocs
(`<<EOF`, `<<-EOF`). Malformed input never raises: an unbalanced file yields
the blocks it could read, and the caller reports what it saw.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

SKIP_DIRS = {".terraform", ".terragrunt-cache", "node_modules", ".git", "cdk.out",
             "__pycache__", ".venv", "venv", "dist", "build"}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")


@dataclass
class Block:
    """One HCL block. `labels` are the quoted names after the block type."""

    kind: str
    labels: list[str]
    attrs: dict[str, str] = field(default_factory=dict)
    blocks: list["Block"] = field(default_factory=list)
    line: int = 0
    file: str = ""
    text: str = ""

    # -- convenience ---------------------------------------------------
    @property
    def address(self) -> str:
        if self.kind == "resource" and len(self.labels) >= 2:
            return f"{self.labels[0]}.{self.labels[1]}"
        if self.kind == "data" and len(self.labels) >= 2:
            return f"data.{self.labels[0]}.{self.labels[1]}"
        if self.kind == "module" and self.labels:
            return f"module.{self.labels[0]}"
        return ".".join([self.kind, *self.labels])

    @property
    def type(self) -> str:
        return self.labels[0] if self.labels else ""

    @property
    def name(self) -> str:
        return self.labels[1] if len(self.labels) > 1 else (self.labels[0] if self.labels else "")

    def child(self, kind: str) -> "Block | None":
        for block in self.blocks:
            if block.kind == kind:
                return block
        return None

    def children(self, kind: str) -> list["Block"]:
        return [block for block in self.blocks if block.kind == kind]

    def find(self, *path: str) -> "Block | None":
        """`find("authorizer_configuration", "custom_jwt_authorizer")`."""
        current: Block | None = self
        for kind in path:
            if current is None:
                return None
            current = current.child(kind)
        return current

    def walk(self) -> Iterator["Block"]:
        yield self
        for block in self.blocks:
            yield from block.walk()

    def get(self, key: str) -> str | None:
        return self.attrs.get(key)

    def literal(self, key: str, default: Any = None) -> Any:
        raw = self.attrs.get(key)
        if raw is None:
            return default
        value = literal(raw)
        return default if value is UNRESOLVED else value

    def has(self, key: str) -> bool:
        return key in self.attrs or self.child(key) is not None


class _Unresolved:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNRESOLVED"


UNRESOLVED: Any = _Unresolved()


# -- lexical helpers --------------------------------------------------------

def strip_comments(text: str) -> str:
    """Blank out comments, keeping strings, heredocs and line numbers intact."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = _skip_string(text, i)
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("<<", i):
            match = re.match(r"<<-?([A-Za-z_][A-Za-z0-9_]*)[ \t]*\n", text[i:])
            if match:
                tag = match.group(1)
                end = re.compile(rf"^[ \t]*{re.escape(tag)}[ \t]*$", re.M)
                found = end.search(text, i + match.end())
                j = found.end() if found else n
                out.append(text[i:j])
                i = j
                continue
        if c == "#" or text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j]))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _skip_string(text: str, i: int) -> int:
    """Return the index just past the string that opens at text[i] == '"'."""
    n = len(text)
    j = i + 1
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return j + 1
        if text.startswith("${", j) or text.startswith("%{", j):
            j = _skip_interpolation(text, j + 2)
            continue
        if c == "\n":
            return j  # unterminated: stop at end of line
        j += 1
    return n


def _skip_interpolation(text: str, j: int) -> int:
    depth = 1
    n = len(text)
    while j < n and depth:
        c = text[j]
        if c == '"':
            j = _skip_string(text, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        j += 1
    return j


def _skip_heredoc(text: str, i: int) -> int | None:
    match = re.match(r"<<-?([A-Za-z_][A-Za-z0-9_]*)[ \t]*\n", text[i:])
    if not match:
        return None
    end = re.compile(rf"^[ \t]*{re.escape(match.group(1))}[ \t]*$", re.M)
    found = end.search(text, i + match.end())
    return found.end() if found else len(text)


def _matching_brace(text: str, i: int) -> int:
    """Index of the `}` matching the `{` at text[i]; len(text) if unbalanced."""
    depth = 0
    n = len(text)
    j = i
    while j < n:
        c = text[j]
        if c == '"':
            j = _skip_string(text, j)
            continue
        if text.startswith("<<", j):
            end = _skip_heredoc(text, j)
            if end is not None:
                j = end
                continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n


def _expression_end(text: str, i: int) -> int:
    """End of an attribute expression starting at i: newline at depth zero."""
    depth = 0
    n = len(text)
    j = i
    while j < n:
        c = text[j]
        if c == '"':
            j = _skip_string(text, j)
            continue
        if text.startswith("<<", j):
            end = _skip_heredoc(text, j)
            if end is not None:
                j = end
                continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif c == "\n" and depth == 0:
            # a trailing operator continues the expression onto the next line
            stripped = text[i:j].rstrip()
            if stripped.endswith(("?", ":", "&&", "||", "+", "-", "*", "/", "==", "!=", ",", "=")):
                j += 1
                continue
            return j
        j += 1
    return n


# -- parsing ----------------------------------------------------------------

def parse(text: str, *, file: str = "") -> list[Block]:
    clean = strip_comments(text)
    return _parse_body(clean, 0, len(clean), file=file, line_offset=0, source=clean)


def _line_of(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def _parse_body(text: str, start: int, end: int, *, file: str, line_offset: int,
                source: str) -> list[Block]:
    blocks: list[Block] = []
    i = start
    attrs_target: dict[str, str] | None = None
    while i < end:
        # skip whitespace
        while i < end and text[i] in " \t\r\n;":
            i += 1
        if i >= end:
            break
        match = _IDENT.match(text, i)
        if not match:
            # not an identifier: skip to the next line
            nl = text.find("\n", i)
            i = end if nl == -1 or nl >= end else nl + 1
            continue
        ident = match.group(0)
        j = match.end()
        labels: list[str] = []
        k = j
        while True:
            while k < end and text[k] in " \t":
                k += 1
            if k < end and text[k] == '"':
                close = _skip_string(text, k)
                labels.append(text[k + 1:close - 1])
                k = close
                continue
            lab = _IDENT.match(text, k)
            if lab and k < end and labels is not None and text[k] != "=" and lab.group(0) and _next_nonspace(text, lab.end(), end) in ("{", '"'):
                labels.append(lab.group(0))
                k = lab.end()
                continue
            break
        if k < end and text[k] == "{":
            close = _matching_brace(text, k)
            block = Block(kind=ident, labels=labels, line=_line_of(source, i), file=file,
                          text=text[i:min(close + 1, end)])
            inner = _parse_body(text, k + 1, min(close, end), file=file, line_offset=0, source=source)
            attrs, children = _split_inner(text, k + 1, min(close, end))
            block.attrs = attrs
            block.blocks = inner
            blocks.append(block)
            i = close + 1
            continue
        if k < end and (text[k] == "=" and not text.startswith("==", k)):
            # an attribute at this level: handled by _split_inner for the parent
            expr_end = _expression_end(text, k + 1)
            i = expr_end + 1
            continue
        nl = text.find("\n", i)
        i = end if nl == -1 or nl >= end else nl + 1
    return blocks


def _next_nonspace(text: str, i: int, end: int) -> str:
    while i < end and text[i] in " \t":
        i += 1
    return text[i] if i < end else ""


def _split_inner(text: str, start: int, end: int) -> tuple[dict[str, str], list]:
    """Collect `key = expr` attributes that sit directly inside a body."""
    attrs: dict[str, str] = {}
    i = start
    while i < end:
        while i < end and text[i] in " \t\r\n;,":
            i += 1
        if i >= end:
            break
        match = _IDENT.match(text, i)
        if not match:
            if text[i] == '"':  # quoted map key
                close = _skip_string(text, i)
                key = text[i + 1:close - 1]
                k = close
            else:
                nl = text.find("\n", i)
                i = end if nl == -1 or nl >= end else nl + 1
                continue
        else:
            key = match.group(0)
            k = match.end()
        while k < end and text[k] in " \t":
            k += 1
        if k < end and text[k] == "=" and not text.startswith("==", k):
            expr_start = k + 1
            expr_end = min(_expression_end(text, expr_start), end)
            attrs[key] = text[expr_start:expr_end].strip()
            i = expr_end + 1
            continue
        # a nested block (or something we do not read): skip past it
        brace = _find_block_open(text, k, end)
        if brace is not None:
            i = _matching_brace(text, brace) + 1
            continue
        nl = text.find("\n", i)
        i = end if nl == -1 or nl >= end else nl + 1
    return attrs, []


def _find_block_open(text: str, k: int, end: int) -> int | None:
    j = k
    while j < end:
        c = text[j]
        if c == "{":
            return j
        if c == '"':
            j = _skip_string(text, j)
            continue
        if c == "\n" or c == "=":
            return None
        j += 1
    return None


# -- values -----------------------------------------------------------------

def literal(raw: str) -> Any:
    """Turn a literal expression into a Python value, or return UNRESOLVED."""
    value = raw.strip()
    if not value:
        return UNRESOLVED
    if value in ("true", "false"):
        return value == "true"
    if value == "null":
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    if value.startswith('"') and _skip_string(value, 0) == len(value):
        inner = value[1:-1]
        if "${" in inner or "%{" in inner:
            return UNRESOLVED
        try:
            return json.loads(value)
        except ValueError:
            return inner
    if value.startswith("[") and value.endswith("]"):
        items = split_top_level(value[1:-1])
        out = []
        for item in items:
            parsed = literal(item)
            if parsed is UNRESOLVED:
                return UNRESOLVED
            out.append(parsed)
        return out
    return UNRESOLVED


def string_or_ref(raw: str | None) -> str | None:
    """A literal string, or the raw reference text if it is not a literal."""
    if raw is None:
        return None
    value = literal(raw)
    if isinstance(value, str):
        return value
    return raw.strip()


def split_top_level(text: str, sep: str = ",") -> list[str]:
    parts: list[str] = []
    depth = 0
    current_start = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[current_start:i])
            current_start = i + 1
        i += 1
    tail = text[current_start:]
    if tail.strip():
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def strings_in(raw: str | None) -> list[str]:
    """Every plain string literal that appears anywhere in an expression."""
    if not raw:
        return []
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == '"':
            j = _skip_string(raw, i)
            out.append(raw[i + 1:j - 1])
            i = j
            continue
        i += 1
    return out


# -- files and projects ----------------------------------------------------

def iter_files(root: Path, suffixes: tuple[str, ...]) -> Iterator[Path]:
    root = Path(root)
    if root.is_file():
        if root.suffix in suffixes or root.name.endswith(suffixes):
            yield root
        return
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and (path.suffix in suffixes or path.name.endswith(suffixes)):
            yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


@dataclass
class TerraformProject:
    root: Path
    files: list[Path] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    lock_versions: dict[str, str] = field(default_factory=dict)
    #: Local module directories outside `root` that were read because a module
    #: block under `root` calls them.
    module_dirs: list[Path] = field(default_factory=list)

    def resources(self, prefix: str = "") -> list[Block]:
        return [b for b in self.blocks if b.kind == "resource" and b.type.startswith(prefix)]

    def resources_of(self, *types: str) -> list[Block]:
        return [b for b in self.blocks if b.kind == "resource" and b.type in types]

    def data_sources(self, prefix: str = "") -> list[Block]:
        return [b for b in self.blocks if b.kind == "data" and b.type.startswith(prefix)]

    def of_kind(self, kind: str) -> list[Block]:
        return [b for b in self.blocks if b.kind == kind]

    def variable_default(self, name: str) -> Any:
        for block in self.of_kind("variable"):
            if block.labels and block.labels[0] == name:
                return block.literal("default")
        return None

    def required_providers(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for block in self.of_kind("terraform"):
            providers = block.child("required_providers")
            if providers is None:
                continue
            for key, raw in providers.attrs.items():
                entry: dict[str, str] = {}
                for part in split_top_level(raw.strip().lstrip("{").rstrip("}"), sep="\n"):
                    for piece in split_top_level(part, sep=","):
                        if "=" in piece:
                            k, v = piece.split("=", 1)
                            entry[k.strip()] = string_or_ref(v.strip()) or ""
                merged = out.setdefault(key, {})
                for k, v in entry.items():
                    merged.setdefault(k, v)
        return out

    def required_version(self) -> str | None:
        for block in self.of_kind("terraform"):
            value = block.literal("required_version")
            if isinstance(value, str):
                return value
        return None

    def address_index(self) -> dict[str, Block]:
        return {b.address: b for b in self.blocks if b.kind in ("resource", "data", "module")}


LOCK_PROVIDER = re.compile(r'provider\s+"([^"]+)"\s*\{(.*?)\n\}', re.S)


def read_lock(path: Path) -> dict[str, str]:
    """`.terraform.lock.hcl` -> {"registry.terraform.io/hashicorp/aws": "6.55.0"}."""
    out: dict[str, str] = {}
    for match in LOCK_PROVIDER.finditer(read_text(path)):
        version = re.search(r'version\s*=\s*"([^"]+)"', match.group(2))
        if version:
            out[match.group(1)] = version.group(1)
    return out


def local_module_dir(call: Block) -> Path | None:
    """The directory a `module` block's local `source` ("./x", "../../modules//x") points at."""
    source = literal(call.get("source") or '""')
    if not isinstance(source, str) or not source.startswith((".", "/")) or "::" in source:
        return None
    base, _, sub = source.partition("//")
    target = (Path(call.file).parent / base / sub) if sub else (Path(call.file).parent / base)
    return target.resolve()


def load_project(root: Path, *, follow_modules: bool = True) -> TerraformProject:
    """Every `.tf` under `root`, plus (by default) the local modules it calls from outside `root`.

    Pointing the reader at one Terragrunt/Terraform environment directory
    (`infrastructure/live/<env>`) therefore sees the resources that environment
    actually deploys through `source = "../../modules/<x>"`, and nothing from a
    sibling environment.
    """
    root = Path(root)
    project = TerraformProject(root=root)
    for path in iter_files(root, (".tf",)):
        project.files.append(path)
        project.blocks.extend(parse(read_text(path), file=str(path)))
    for lock in iter_files(root, (".terraform.lock.hcl",)):
        for provider, version in read_lock(lock).items():
            project.lock_versions.setdefault(provider, version)
    if follow_modules:
        loaded = {p.resolve().parent for p in project.files}
        pending = [b for b in project.blocks if b.kind == "module"]
        while pending:
            directory = local_module_dir(pending.pop())
            if directory is None or directory in loaded or not directory.is_dir():
                continue
            loaded.add(directory)
            project.module_dirs.append(directory)
            for path in sorted(directory.glob("*.tf")):
                blocks = parse(read_text(path), file=str(path))
                project.files.append(path)
                project.blocks.extend(blocks)
                pending.extend(b for b in blocks if b.kind == "module")
    return project


def version_tuple(text: str | None) -> tuple[int, ...]:
    if not text:
        return ()
    numbers = re.findall(r"\d+", text)
    return tuple(int(n) for n in numbers[:3])
