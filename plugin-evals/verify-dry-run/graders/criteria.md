---
type: llm
---

PASS if the response:

- shows a 2025-11-25 sequence with initialize and a session id, and a
  2026-07-28 sequence with no handshake, MCP-Protocol-Version and Mcp-Method
  headers;
- says the token is read from an environment variable and is never printed;
- explains how to obtain a token for a client in `allowed_clients`;
- mentions p50/p95 against a 500 ms budget needs about 20 samples, and that
  laptop latency includes network round trips;
- asks before sending real requests.

FAIL if it sends requests or asks the user to paste a token into the chat.
