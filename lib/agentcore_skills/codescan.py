"""Read application code, CDK and container files for AgentCore-relevant facts.

The questions are always the same few: which agent framework is this, does it
already talk to AgentCore (and through which door: boto3, the AgentCore Python
SDK, the AgentCore CLI's `agentcore.json`, the deprecated starter toolkit's
`.bedrock_agentcore.yaml`, CDK constructs), is there an MCP server, how is it
instrumented, and what does its container look like. Python is read with
`ast` (imports and decorators are exact); TypeScript, JavaScript and CDK are
matched by pattern, line by line, which is enough to locate and cite but never
enough to prove absence — reports say "not found", never "does not exist".
Nothing here imports or executes the code it reads.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .hcl import SKIP_DIRS, read_text

#: import root -> framework label
PY_FRAMEWORKS = {
    "strands": "strands",
    "langgraph": "langgraph",
    "langchain": "langchain",
    "claude_agent_sdk": "claude-agent-sdk",
    "crewai": "crewai",
    "llama_index": "llamaindex",
    "google.adk": "google-adk",
    "agents": "openai-agents",
    "autogen": "autogen",
    "pydantic_ai": "pydantic-ai",
}
JS_FRAMEWORKS = {
    "@strands-agents/sdk": "strands",
    "@langchain/langgraph": "langgraph",
    "@anthropic-ai/claude-agent-sdk": "claude-agent-sdk",
    "@openai/agents": "openai-agents",
    "@mastra/core": "mastra",
    "ai": "vercel-ai-sdk",
}
JS_MCP = ("@modelcontextprotocol/sdk", "@modelcontextprotocol/server", "@modelcontextprotocol/node")
JS_TRACING = {
    "aws-xray-sdk": "aws-xray-sdk",
    "aws-xray-sdk-core": "aws-xray-sdk",
    "@aws-lambda-powertools/tracer": "powertools-tracer",
    "@opentelemetry/api": "opentelemetry",
    "@opentelemetry/sdk-node": "opentelemetry",
    "@aws/aws-distro-opentelemetry-node-autoinstrumentation": "adot",
}
PY_TRACING = {
    "aws_xray_sdk": "aws-xray-sdk",
    "opentelemetry": "opentelemetry",
    "aws_opentelemetry_distro": "adot",
}
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs")


@dataclass
class CodeFacts:
    frameworks: dict[str, list[str]] = field(default_factory=dict)       # label -> files
    agentcore_sdk: list[dict[str, Any]] = field(default_factory=list)    # python SDK usage
    boto3_clients: list[dict[str, Any]] = field(default_factory=list)    # bedrock-agentcore[-control]
    js_agentcore: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    tracing: dict[str, list[str]] = field(default_factory=dict)
    identity_decorators: list[dict[str, Any]] = field(default_factory=list)
    entrypoints: list[dict[str, Any]] = field(default_factory=list)
    routes: dict[str, list[str]] = field(default_factory=dict)            # "/ping" -> files
    stateless_http: list[str] = field(default_factory=list)
    dockerfiles: list[dict[str, Any]] = field(default_factory=list)
    cdk: list[dict[str, Any]] = field(default_factory=list)
    agentcore_cli_projects: list[str] = field(default_factory=list)       # agentcore.json
    starter_toolkit_configs: list[str] = field(default_factory=list)      # .bedrock_agentcore.yaml
    package_json: list[dict[str, Any]] = field(default_factory=list)
    requirements: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, bucket: dict[str, list[str]], key: str, path: str) -> None:
        bucket.setdefault(key, [])
        if path not in bucket[key]:
            bucket[key].append(path)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def iter_project_files(root: Path):
    root = Path(root)
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel):
            continue
        if path.is_file():
            yield path


def scan(root: Path) -> CodeFacts:
    facts = CodeFacts()
    root = Path(root)
    for path in iter_project_files(root):
        rel = str(path.relative_to(root)) if root.is_dir() else path.name
        name = path.name
        if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile") or name == "Containerfile":
            facts.dockerfiles.append(read_dockerfile(path, rel))
        elif name == "agentcore.json":
            facts.agentcore_cli_projects.append(rel)
        elif name in (".bedrock_agentcore.yaml", ".bedrock_agentcore.yml"):
            facts.starter_toolkit_configs.append(rel)
        elif name == "package.json":
            _scan_package_json(facts, path, rel)
        elif name in ("requirements.txt", "pyproject.toml") or (name.startswith("requirements") and name.endswith(".txt")):
            _scan_requirements(facts, path, rel)
        elif path.suffix == ".py":
            _scan_python(facts, path, rel)
        elif path.suffix in (".ts", ".tsx", ".js", ".mjs", ".cjs") and not name.endswith(".d.ts"):
            _scan_js(facts, path, rel)
    return facts


# -- python -----------------------------------------------------------------

def _scan_python(facts: CodeFacts, path: Path, rel: str) -> None:
    text = read_text(path)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        facts.errors.append(f"{rel}: syntax error at line {exc.lineno}")
        return
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            for alias in node.names:
                imported.add(f"{node.module}.{alias.name}")
    for module in imported:
        for root_name, label in PY_FRAMEWORKS.items():
            if module == root_name or module.startswith(root_name + "."):
                if root_name == "agents" and "agents.Agent" not in imported:
                    continue
                facts.add(facts.frameworks, label, rel)
        for root_name, label in PY_TRACING.items():
            if module == root_name or module.startswith(root_name + "."):
                facts.add(facts.tracing, label, rel)
        if module.startswith("bedrock_agentcore"):
            facts.agentcore_sdk.append({"file": rel, "import": module})
        if module in ("mcp.server.fastmcp", "fastmcp", "mcp.server") or module.startswith("mcp.server.fastmcp"):
            facts.mcp_servers.append({"file": rel, "kind": "python-fastmcp" if "fastmcp" in module else "python-mcp"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _call_name(node.func)
            if fn.endswith("client") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("bedrock-agentcore"):
                    facts.boto3_clients.append({"file": rel, "service": arg.value, "line": node.lineno})
            for kw in node.keywords:
                if kw.arg == "stateless_http" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    facts.stateless_http.append(rel)
            if fn.endswith(".run") or fn == "run":
                for kw in node.keywords:
                    if kw.arg == "transport" and isinstance(kw.value, ast.Constant) and kw.value.value == "streamable-http":
                        facts.add(facts.routes, "/mcp", rel)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                name = _call_name(deco.func if isinstance(deco, ast.Call) else deco)
                if name.endswith("entrypoint"):
                    facts.entrypoints.append({"file": rel, "function": node.name, "line": node.lineno})
                    facts.add(facts.routes, "/invocations", rel)
                    facts.add(facts.routes, "/ping", rel)  # BedrockAgentCoreApp serves /ping
                if name.endswith("ping"):
                    facts.add(facts.routes, "/ping", rel)
                if name.split(".")[-1] in ("requires_access_token", "requires_api_key"):
                    entry = {"file": rel, "function": node.name, "line": node.lineno, "decorator": name.split(".")[-1]}
                    if isinstance(deco, ast.Call):
                        for kw in deco.keywords:
                            if isinstance(kw.value, ast.Constant):
                                entry[kw.arg] = kw.value.value
                    facts.identity_decorators.append(entry)
                route = _route_of(deco)
                if route:
                    facts.add(facts.routes, route, rel)
    if "BedrockAgentCoreApp" in text:
        facts.add(facts.routes, "/ping", rel)
        facts.add(facts.routes, "/invocations", rel)


def _route_of(deco: ast.expr) -> str | None:
    if isinstance(deco, ast.Call) and deco.args and isinstance(deco.args[0], ast.Constant):
        value = deco.args[0].value
        name = _call_name(deco.func)
        if isinstance(value, str) and value.startswith("/") and name.split(".")[-1] in ("get", "post", "route", "api_route"):
            return value
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


# -- javascript / typescript --------------------------------------------------

IMPORT_RE = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*|import\s+)["']([^"']+)["']""")
ROUTE_RE = re.compile(r"""["'`](GET|POST|PUT|DELETE)?\s*(/ping|/invocations|/mcp|/health|/ready)["'`]""")
CDK_RE = re.compile(r"(aws-bedrockagentcore|aws_bedrockagentcore|Cfn(Runtime|Gateway|GatewayTarget|Memory|WorkloadIdentity|OAuth2CredentialProvider|ApiKeyCredentialProvider)\b|@aws/agentcore-cdk|agentcore-cdk)")


#: An in-repo X-Ray emitter: code that reads the Lambda trace header or the
#: daemon address and therefore writes its own (sub)segments without an SDK.
XRAY_EMITTER_RE = re.compile(r"\b(?:AWS_XRAY_DAEMON_ADDRESS|_X_AMZN_TRACE_ID)\b")


def _scan_js(facts: CodeFacts, path: Path, rel: str) -> None:
    text = read_text(path)
    if XRAY_EMITTER_RE.search(text) and not rel.endswith((".test.ts", ".spec.ts", ".test.js")):
        facts.add(facts.tracing, "xray-emitter", rel)
    for match in IMPORT_RE.finditer(text):
        module = match.group(1)
        for name, label in JS_FRAMEWORKS.items():
            if module == name or (name != "ai" and module.startswith(name + "/")):
                facts.add(facts.frameworks, label, rel)
        if module.startswith(JS_MCP) and ("server" in module or module.endswith("/node") or "mcp.js" in module):
            facts.mcp_servers.append({"file": rel, "kind": "typescript-mcp", "module": module})
        for name, label in JS_TRACING.items():
            if module == name or module.startswith(name + "/"):
                facts.add(facts.tracing, label, rel)
        if module.startswith("@aws-sdk/client-bedrock-agentcore"):
            facts.js_agentcore.append(rel)
    for match in ROUTE_RE.finditer(text):
        facts.add(facts.routes, match.group(2), rel)
    cdk = CDK_RE.search(text)
    if cdk:
        facts.cdk.append({"file": rel, "match": cdk.group(0), "language": "typescript"})


def _scan_package_json(facts: CodeFacts, path: Path, rel: str) -> None:
    try:
        doc = json.loads(read_text(path) or "{}")
    except ValueError:
        facts.errors.append(f"{rel}: not valid JSON")
        return
    deps = {**doc.get("dependencies", {}), **doc.get("devDependencies", {})}
    facts.package_json.append({"file": rel, "name": doc.get("name"), "dependencies": sorted(deps)})
    for dep in deps:
        for name, label in JS_TRACING.items():
            if dep == name:
                facts.add(facts.tracing, label, rel)
        if dep in ("aws-cdk-lib", "@aws/agentcore-cdk"):
            facts.cdk.append({"file": rel, "match": dep, "language": "typescript"})
        if dep.startswith(JS_MCP):
            facts.mcp_servers.append({"file": rel, "kind": "typescript-mcp", "module": dep, "declared_only": True})
        for name, label in JS_FRAMEWORKS.items():
            if dep == name and name != "ai":
                facts.add(facts.frameworks, label, rel)


def _scan_requirements(facts: CodeFacts, path: Path, rel: str) -> None:
    names: list[str] = []
    for line in read_text(path).splitlines():
        line = line.strip().strip('",')
        if not line or line.startswith(("#", "[", "-")):
            continue
        match = re.match(r"([A-Za-z0-9_.\-]+)", line)
        if match:
            names.append(match.group(1).lower())
    facts.requirements[rel] = names
    for name in names:
        if name in ("aws-opentelemetry-distro",):
            facts.add(facts.tracing, "adot", rel)
        if name in ("aws-cdk-lib",):
            facts.cdk.append({"file": rel, "match": name, "language": "python"})


# -- containers ---------------------------------------------------------------

def read_dockerfile(path: Path, rel: str) -> dict[str, Any]:
    text = read_text(path)
    facts: dict[str, Any] = {"file": rel, "from": [], "platform": [], "expose": [], "cmd": None,
                             "entrypoint": None, "user": None, "copies_env": False, "otel": False}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        head = head.upper()
        if head == "FROM":
            facts["from"].append(rest)
            platform = re.search(r"--platform=(\S+)", rest)
            if platform:
                facts["platform"].append(platform.group(1))
        elif head == "EXPOSE":
            facts["expose"].extend(re.findall(r"\d+", rest))
        elif head == "CMD":
            facts["cmd"] = rest
        elif head == "ENTRYPOINT":
            facts["entrypoint"] = rest
        elif head == "USER":
            facts["user"] = rest
        elif head in ("COPY", "ADD"):
            tokens = [t for t in rest.split() if not t.startswith("--")]
            if any(t == ".env" or t.startswith(".env.") for t in tokens[:-1]):
                facts["copies_env"] = True
        if "opentelemetry-instrument" in line or "OTEL_" in line:
            facts["otel"] = True
    facts["arm64"] = any("arm64" in p for p in facts["platform"]) or "arm64" in text.lower()
    return facts
