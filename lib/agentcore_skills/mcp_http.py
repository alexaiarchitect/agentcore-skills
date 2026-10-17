"""A minimal MCP Streamable HTTP client in the standard library, for probing.

`agentcore-verify` needs to ask a deployed AgentCore Gateway (or any MCP
endpoint) two questions — "what tools do you list?" and "does one call
work, and how long does it take?" — in either of the two protocol eras a
gateway can speak:

* **2025-03-26 … 2025-11-25 (sessionful).** `initialize` first; the response
  carries `Mcp-Session-Id`; send `notifications/initialized`; then every
  request repeats the session id and `MCP-Protocol-Version`.
* **2026-07-28 (stateless).** No handshake and no session. Every request
  carries `MCP-Protocol-Version: 2026-07-28`, an `Mcp-Method` header, and
  `params._meta` with `io.modelcontextprotocol/protocolVersion`,
  `/clientInfo` and `/clientCapabilities`.

Responses may be `application/json` or a `text/event-stream` whose `data:`
lines hold JSON-RPC messages; both are read. The bearer token is passed in by
the caller (read from an environment variable the user names) and is never
logged — `redact()` is applied to anything printed.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

CLIENT_INFO = {"name": "agentcore-skills-verify", "version": "0.1.0"}
STATELESS = "2026-07-28"


class McpError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "",
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.headers = headers or {}


@dataclass
class Exchange:
    method: str
    status: int
    elapsed_ms: float
    response: dict[str, Any] | None
    headers: dict[str, str] = field(default_factory=dict)


def redact(headers: dict[str, str]) -> dict[str, str]:
    out = {}
    for key, value in headers.items():
        if key.lower() in ("authorization", "x-api-key", "cookie"):
            out[key] = value.split(" ", 1)[0] + " ***" if " " in value else "***"
        else:
            out[key] = value
    return out


def parse_body(body: bytes, content_type: str) -> list[dict[str, Any]]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    if "text/event-stream" in content_type or text.startswith(("data:", "event:", "id:")):
        messages = []
        buffer: list[str] = []
        for line in text.splitlines() + [""]:
            if line.startswith("data:"):
                buffer.append(line[5:].lstrip())
            elif not line.strip() and buffer:
                try:
                    messages.append(json.loads("\n".join(buffer)))
                except ValueError:
                    pass
                buffer = []
        return messages
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise McpError(f"response is not JSON: {text[:120]!r}") from exc
    return doc if isinstance(doc, list) else [doc]


class Client:
    def __init__(self, url: str, *, protocol: str = "2025-11-25", token: str | None = None,
                 timeout: float = 15.0, extra_headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.protocol = protocol
        self.token = token
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.session_id: str | None = None
        self.negotiated: str | None = None
        self.server_info: dict[str, Any] | None = None
        self._id = 0
        self.exchanges: list[Exchange] = []

    @property
    def stateless(self) -> bool:
        return self.protocol == STATELESS

    def headers_for(self, method: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   **self.extra_headers}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if method != "initialize" or self.stateless:
            headers["MCP-Protocol-Version"] = self.negotiated or self.protocol
        if self.stateless:
            headers["Mcp-Method"] = method
        if self.session_id and not self.stateless:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def payload_for(self, method: str, params: dict[str, Any] | None, *, notify: bool = False) -> dict[str, Any]:
        params = dict(params or {})
        if self.stateless:
            meta = dict(params.get("_meta") or {})
            meta.setdefault("io.modelcontextprotocol/protocolVersion", self.protocol)
            meta.setdefault("io.modelcontextprotocol/clientInfo", CLIENT_INFO)
            meta.setdefault("io.modelcontextprotocol/clientCapabilities", {})
            params["_meta"] = meta
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            message["params"] = params
        if not notify:
            self._id += 1
            message["id"] = f"verify-{self._id}"
        return message

    def _post(self, method: str, message: dict[str, Any]) -> Exchange:
        data = json.dumps(message).encode("utf-8")
        request = urllib.request.Request(self.url, data=data, method="POST", headers=self.headers_for(method))
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status = response.status
                headers = {k: v for k, v in response.headers.items()}
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            raise McpError(f"HTTP {exc.code} for {method}", status=exc.code,
                           body=body.decode("utf-8", errors="replace")[:500],
                           headers={k: v for k, v in (exc.headers or {}).items()}) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise McpError(f"could not reach {self.url}: {getattr(exc, 'reason', exc)}") from None
        elapsed = (time.perf_counter() - started) * 1000.0
        messages = parse_body(body, headers.get("Content-Type", headers.get("content-type", "")))
        response_msg = None
        for msg in messages:
            if isinstance(msg, dict) and msg.get("id") == message.get("id"):
                response_msg = msg
        if response_msg is None and messages and "id" in message:
            response_msg = messages[-1] if isinstance(messages[-1], dict) else None
        exchange = Exchange(method=method, status=status, elapsed_ms=elapsed, response=response_msg, headers=headers)
        self.exchanges.append(exchange)
        return exchange

    def request(self, method: str, params: dict[str, Any] | None = None) -> Exchange:
        exchange = self._post(method, self.payload_for(method, params))
        if exchange.response and "error" in exchange.response:
            err = exchange.response["error"]
            raise McpError(f"JSON-RPC error {err.get('code')} on {method}: {err.get('message')}",
                           status=exchange.status, body=json.dumps(err)[:500])
        return exchange

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._post(method, self.payload_for(method, params, notify=True))

    def initialize(self) -> Exchange | None:
        if self.stateless:
            return None
        exchange = self.request("initialize", {"protocolVersion": self.protocol, "capabilities": {},
                                               "clientInfo": CLIENT_INFO})
        lower = {k.lower(): v for k, v in exchange.headers.items()}
        self.session_id = lower.get("mcp-session-id")
        result = (exchange.response or {}).get("result") or {}
        self.negotiated = result.get("protocolVersion") or self.protocol
        self.server_info = result.get("serverInfo")
        self.notify("notifications/initialized")
        return exchange

    def list_tools(self) -> tuple[list[dict[str, Any]], Exchange]:
        tools: list[dict[str, Any]] = []
        cursor = None
        first: Exchange | None = None
        for _ in range(50):
            exchange = self.request("tools/list", {"cursor": cursor} if cursor else None)
            first = first or exchange
            result = (exchange.response or {}).get("result") or {}
            tools.extend(result.get("tools") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                break
        assert first is not None
        return tools, first

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Exchange:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def ping(url: str, timeout: float = 5.0) -> tuple[int, dict[str, Any] | None, float]:
    """GET a Runtime container's /ping. Returns (status, body, elapsed_ms)."""
    started = time.perf_counter()
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        return exc.code, None, (time.perf_counter() - started) * 1000.0
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise McpError(f"could not reach {url}: {getattr(exc, 'reason', exc)}") from None
    try:
        doc = json.loads(body)
    except ValueError:
        doc = None
    return status, doc if isinstance(doc, dict) else None, (time.perf_counter() - started) * 1000.0
