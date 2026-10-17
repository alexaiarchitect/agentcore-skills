---
type: llm
---

PASS if the response says no, and names: the image is not linux/arm64; it
exposes 5000, not 8000; the server binds 127.0.0.1; FastMCP is not stateless
(`stateless_http=True` needed, and the platform's `Mcp-Session-Id` must be
accepted); `.env` is copied into the image and whatever it held must be
rotated. It offers to generate a Dockerfile and asks first.

FAIL if it says the server can run as is, or treats the copied `.env` as a
style issue.
