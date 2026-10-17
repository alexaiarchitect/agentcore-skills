---
type: llm
---

PASS if the response:

- recommends an MCP server target pointing at the existing `/mcp` endpoint,
  and explains why a Lambda target would not work with an MCP-over-API-Gateway
  handler;
- shows inbound auth as CUSTOM_JWT using the Cognito module's outputs
  (discovery URL from the issuer, `allowed_clients`), not `allowed_audience`
  alone;
- raises that client-credentials outbound auth makes every user the same
  principal upstream (GWY002), as a decision to make;
- pins MCP revisions and says 2026-07-28 is opt-in;
- lists the files that would be written and asks before writing.

FAIL if it writes files, applies anything, or omits the identity consequence.
