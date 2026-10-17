---
type: llm
---

PASS if the response:

- uses the discovery URL form ending in `/.well-known/openid-configuration`;
- restricts inbound with `allowed_clients` and explains that Cognito access
  tokens carry `client_id`, with `aud` only under a resource binding and never
  in client-credentials tokens;
- plans outbound as a dedicated client-credentials app client plus a
  `CustomOauth2` credential provider with write-only secrets;
- says the upstream's own JWT authorizer must accept the new client id;
- explains that the upstream will see the gateway, not the user, and names at
  least one way to keep user identity (token exchange, a signed claim via an
  interceptor, Runtime passthrough).

FAIL if it puts a client secret in a file, or presents client credentials as
preserving per-user identity.
