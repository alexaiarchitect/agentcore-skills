# Keeping the end user's identity across the gateway

## The problem

An upstream that derives the owner of data from the token — the first user's
server computes `owner = base64url(SHA-256(issuer + NUL + subject))` and
rejects owner identifiers in arguments — sees only the token it receives. With
an MCP server target using **client credentials**, that token belongs to the
gateway's outbound client, so every user becomes the same owner. That is not
a misconfiguration the review can fix; it is a design choice (`GWY002`,
`IDN006`).

## The options (checked 2026-10-05)

| Option | How | What is verified | Cost / caveat |
|---|---|---|---|
| **A. Token exchange (on-behalf-of)** | target `oauth` with grant `TOKEN_EXCHANGE`; the gateway exchanges the inbound user token for a target-scoped token | documented for MCP server and OpenAPI targets; AWS now calls it the recommended production pattern | needs an identity provider that supports RFC 8693 token exchange. Amazon Cognito's token endpoint accepts only `authorization_code`, `refresh_token` and `client_credentials` (first user's finding) — not with Cognito |
| **B. Authorization code (3LO) per user** | target `oauth` with `AUTHORIZATION_CODE`; each user consents once; per-user tokens in the vault | documented | an interactive consent step, and the URL is valid for 10 minutes; awkward for voice-only clients |
| **C. Interceptor forwards the user's JWT** (`--interceptor forward-jwt`) | a Lambda `REQUEST` interceptor (`pass_request_headers = true`) copies the inbound bearer token — already validated by the gateway's `CUSTOM_JWT` authorizer — into `params._meta["<meta key>"]`; the upstream **re-verifies it** like a header token | interceptors exist, see headers when asked, may replace an MCP target's request **body** (`transformedGatewayRequest.body`), not its headers | no shared secret; the proof stays the IdP's signature. The token travels one hop further (inside the body), so nothing may log bodies. One Lambda invocation per call |
| **C′. Interceptor signs a claim** (`--interceptor signed-claim`) | the interceptor decodes the validated token and signs a short-lived HS256 claim (`sub`, `user_iss`, `client_id`, `scope`, `exp`) with a Secrets Manager key | as C | a shared secret between interceptor and upstream; the upstream trusts the interceptor's word, not the IdP's signature; key rotation is yours |
| **D. Host the server on Runtime, or use an HTTP target** | `JWT_PASSTHROUGH` outbound: the gateway forwards the validated inbound token unchanged | "`JWT_PASSTHROUGH` is only available for HTTP targets (passthrough and AgentCore Runtime)"; it needs a JWT-bearing inbound type (`CUSTOM_JWT` or `NONE`), **not** `AUTHENTICATE_ONLY`, which is SigV4 and carries no bearer token | a different target type than an MCP-server target; AWS calls passthrough not recommended for production (same token accepted by gateway and target) |
| **E. No gateway on the user path** | keep clients on the existing endpoint; use the gateway only for agent-to-tool traffic that is not per-user | — | gives up the gateway for that path |

The AWS pages disagree on one point: the outbound-auth page still says token
passthrough "requires the gateway to use `AUTHENTICATE_ONLY` inbound
authorization", while the inbound-auth page says passthrough "is not available
with `AUTHENTICATE_ONLY`, which is SigV4-based and carries no bearer token".
The plugin follows the inbound-auth page (it is the one that defines the
types) and records the conflict in `.dev/VERIFIED-FACTS.md`.

## Choosing

- If the issuer supports token exchange, **A** is the clean answer: the
  upstream keeps validating a real user token.
- If it does not (Cognito), **C** keeps the upstream where it is at the cost
  of one interceptor hop, and needs no new secret. Prefer it over **C′**.
- **D** is the most AgentCore-native and the largest change.

## Generating C (or C′)

```
gateway_plan.py <project> --upstream mcp --outbound oauth --with-identity \
    --interceptor forward-jwt --meta-key com.example/end-user-token --out-dir infrastructure/modules
```

writes `agentcore-gateway/` (with `interceptor_configuration`: `REQUEST`,
`pass_request_headers = true`, and `lambda:InvokeFunction` for the gateway
role), `agentcore-identity/` and `agentcore-gateway-interceptor/` (the
`src/index.mjs` handler, its role with basic execution and X-Ray, a log group,
the function on `nodejs22.x`/arm64, output `function_arn`). An existing
interceptor is wired with `--interceptor arn:aws:lambda:...` instead.

The generated handler, for every JSON-RPC message in the body: **removes**
any client-supplied `_meta["<meta key>"]` first (only the interceptor may set
it), then sets it to the caller's bearer token (C) or the signed claim (C′).
It logs nothing.

## What the upstream must do (C)

1. Verify its own bearer token as today (signature, issuer, expiry, client
   in the allow list, audience/scopes of this resource).
2. Only if that token's `client_id` is the gateway's outbound client, read
   `params._meta["<meta key>"]`; verify it **exactly** like a header token;
   reject it if it is itself a gateway token; then act as that user.
3. Otherwise ignore the key; in every case delete it before the MCP SDK sees
   the request, and never log request bodies.

For C′ step 2 becomes: verify the HS256 signature with the shared key, `iss`,
`aud` (this endpoint) and `exp`, and take the owner from `user_iss` + `sub`.

The first real deployment of C is in the first user's repository (a
gateway-interceptor app beside the MCP server handler).

**Not documented, check after the first apply:** that the gateway keeps
`params._meta` intact on its way to an MCP-server target. Prove it: call
through the gateway as two different users and confirm the upstream records
two different owners (`verify.py` with each user's token, then the upstream's
logs). If `_meta` is dropped, fall back to C′ in another field, or E.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-building-adding-targets-authorization.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-interceptors.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-interceptors-types.html,
https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html,
https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/bedrockagentcore_gateway.html.markdown
(all read 2026-10-05); the first user's authentication and
identity-passthrough notes (private) for the owner derivation and the
deployed option C.
