"""`agentcore-verify` against a local fake gateway (127.0.0.1, no AWS)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agentcore_skills.report import EXIT_FINDINGS, EXIT_INCONCLUSIVE, EXIT_OK, EXIT_USAGE

VERIFY = "skills/agentcore-verify/scripts/verify.py"
AWS = "skills/agentcore-verify/scripts/aws_checks.py"
TOKEN = "test-token-not-a-secret"
TOOLS = [{"name": "vault___list_categories", "inputSchema": {"type": "object"}},
         {"name": "vault___query_records", "inputSchema": {"type": "object"}}]


class FakeGateway(BaseHTTPRequestHandler):
    """Speaks just enough MCP: sessionful 2025-11-25 and stateless 2026-07-28."""

    seen: list[dict] = []
    mode = "ok"

    def log_message(self, *args):  # silence
        pass

    def _send(self, status, body, headers=None, sse=False):
        payload = json.dumps(body)
        data = (f"event: message\ndata: {payload}\n\n" if sse else payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ping":
            status = "Healthy" if FakeGateway.mode != "sick" else "Unhealthy"
            return self._send(200, {"status": status})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        headers = {k.lower(): v for k, v in self.headers.items()}
        FakeGateway.seen.append({"method": body.get("method"), "headers": headers, "body": body})
        if headers.get("authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"message": "Unauthorized"}, {"WWW-Authenticate": 'Bearer error="invalid_token"'})
        version = headers.get("mcp-protocol-version")
        method = body.get("method")
        if method == "initialize":
            return self._send(200, {"jsonrpc": "2.0", "id": body["id"], "result": {
                "protocolVersion": body["params"]["protocolVersion"], "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-gateway", "version": "1"}}}, {"Mcp-Session-Id": "session-123"})
        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return None
        if version == "2026-07-28":
            meta = (body.get("params") or {}).get("_meta") or {}
            if headers.get("mcp-method") != method or meta.get("io.modelcontextprotocol/protocolVersion") != version:
                return self._send(400, {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32600, "message": "bad stateless request"}})
        elif headers.get("mcp-session-id") != "session-123":
            return self._send(400, {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32600, "message": "no session"}})
        if method == "tools/list":
            return self._send(200, {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": TOOLS}}, sse=True)
        if method == "tools/call":
            failing = FakeGateway.mode == "tool-error"
            return self._send(200, {"jsonrpc": "2.0", "id": body["id"], "result": {
                "content": [{"type": "text", "text": "boom" if failing else "[]"}], "isError": failing}})
        return self._send(200, {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "nope"}})


@pytest.fixture
def gateway():
    FakeGateway.seen = []
    FakeGateway.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


ENV = {"GATEWAY_TOKEN": TOKEN, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}


def test_sessionful_probe_lists_and_calls(run_script, gateway):
    result = run_script(VERIFY, "--gateway-url", f"{gateway}/mcp", "--call", "query_records", "--samples", "5",
                        "--expect-tool", "list_categories", "--json", env=ENV)
    assert result.returncode == EXIT_OK, result.stdout
    probe = result.json()["discovered"]["gateway"][0]
    assert probe["session_id_issued"] and probe["called"] == "vault___query_records"
    assert probe["latency"]["count"] == 5
    methods = [s["method"] for s in FakeGateway.seen]
    assert methods[:3] == ["initialize", "notifications/initialized", "tools/list"]


def test_stateless_probe_sends_headers_and_meta(run_script, gateway):
    result = run_script(VERIFY, "--gateway-url", f"{gateway}/mcp", "--protocol", "2026-07-28", "--json", env=ENV)
    assert result.returncode == EXIT_OK, result.stdout
    assert "initialize" not in [s["method"] for s in FakeGateway.seen]
    first = FakeGateway.seen[0]
    assert first["headers"]["mcp-method"] == "tools/list" and "mcp-session-id" not in first["headers"]


def test_both_revisions_are_compared(run_script, gateway):
    result = run_script(VERIFY, "--gateway-url", f"{gateway}/mcp", "--protocol", "both", "--json", env=ENV)
    probes = result.json()["discovered"]["gateway"]
    assert [p["protocol"] for p in probes] == ["2025-11-25", "2026-07-28"]
    assert "VER011" not in result.ids()


def test_a_refused_token(run_script, gateway):
    result = run_script(VERIFY, "--gateway-url", f"{gateway}/mcp", "--json", env={**ENV, "GATEWAY_TOKEN": "wrong"})
    assert "VER002" in result.ids() and result.returncode == EXIT_FINDINGS
    assert "wrong" not in result.stdout, "the token is never printed"


def test_tool_errors_budget_and_missing_tools(run_script, gateway):
    FakeGateway.mode = "tool-error"
    result = run_script(VERIFY, "--gateway-url", f"{gateway}/mcp", "--call", "query_records", "--expect-tool", "nope",
                        "--budget-ms", "0.001", "--json", env=ENV)
    assert {"VER004", "VER008", "VER005"} <= result.ids()


def test_ping(run_script, gateway):
    assert run_script(VERIFY, "--ping-url", f"{gateway}/ping", "--json", env=ENV).returncode == EXIT_OK
    FakeGateway.mode = "sick"
    assert "VER009" in run_script(VERIFY, "--ping-url", f"{gateway}/ping", "--json", env=ENV).ids()


def test_unreachable_is_inconclusive(run_script):
    result = run_script(VERIFY, "--gateway-url", "http://127.0.0.1:9/mcp", "--timeout", "2", "--json", env=ENV)
    assert result.returncode == EXIT_INCONCLUSIVE and "VER001" in result.ids()


def test_dry_run_sends_nothing_and_redacts(run_script, gateway):
    result = run_script(VERIFY, "--gateway-url", f"{gateway}/mcp", "--protocol", "both", "--call", "x", "--dry-run",
                        "--json", env=ENV)
    assert result.returncode == EXIT_OK and FakeGateway.seen == []
    assert TOKEN not in result.stdout and "Bearer ***" in result.stdout
    stateless = [r for r in result.json()["requests"] if r["protocol"] == "2026-07-28"]
    assert stateless[0]["headers"]["Mcp-Method"] == "tools/list"


def test_usage_errors(run_script):
    assert run_script(VERIFY).returncode == EXIT_USAGE
    assert run_script(VERIFY, "--gateway-url", "http://x/mcp", "--args", "{bad").returncode == EXIT_USAGE


def test_aws_checks_emit_commands_only(run_script, project):
    doc = run_script(AWS, project("gateway_good"), "--gateway-id", "gw-123", "--json").json()
    commands = " ".join(c["cmd"] for c in doc["commands"])
    assert "--region eu-central-1" in commands and "get-gateway" in commands and "gw-123" in commands
    assert "get-trace-summaries" in commands and "responsetime > 0.5" in commands
    assert doc["note"] == "nothing was run"
