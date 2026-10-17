# Inbound JWT from Amazon Cognito

## Authorizer types

| `authorizer_type` | Meaning |
|---|---|
| `CUSTOM_JWT` | the gateway validates a bearer JWT against an OIDC issuer |
| `AWS_IAM` | callers sign with SigV4 |
| `AUTHENTICATE_ONLY` | the gateway verifies the caller's SigV4 signature but makes no authorization decision: any authenticated IAM principal may invoke it. It carries no bearer token, so it is **not** usable with token passthrough (corrected 2026-10-05; see below) |
| `NONE` | no authentication or authorization at the gateway (`ACR010`) |

The inbound-auth page (re-read 2026-10-05) says verbatim: "With
authenticate-only authorization (`AUTHENTICATE_ONLY`), the gateway verifies the
caller's Signature Version 4 (SigV4) signature to confirm their identity, but
does not make any authorization decision of its own", and that token
passthrough "requires a JWT-bearing inbound type — JWT inbound authorization
or `NONE`. It is not available with `AUTHENTICATE_ONLY`". The outbound-auth
page still says passthrough requires `AUTHENTICATE_ONLY`; the two AWS pages
conflict, and this plugin follows the inbound-auth page. Version 0.1.0 of this
file said "used with token passthrough", which was wrong.

## `custom_jwt_authorizer` fields

| Terraform | API | Checks |
|---|---|---|
| `discovery_url` | `discoveryUrl` | the issuer's full OIDC configuration URL, **including** `/.well-known/openid-configuration` |
| `allowed_clients` | `allowedClients` | the token's `client_id` claim |
| `allowed_audience` | `allowedAudience` | the token's `aud` claim |
| `allowed_scopes` | `allowedScopes` | scopes the token must carry |
| `custom_claim` | `customClaims` | required claim values and match rules |

## Cognito specifics

Discovery URL:

```
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>/.well-known/openid-configuration
```

When the pool lives in a child module, build it from that module's outputs:
`"${module.identity.issuer}/.well-known/openid-configuration"` when the module
exports the issuer (`https://${aws_cognito_user_pool.x.endpoint}`), otherwise
from an exported pool id. `gateway_plan.py` finds these outputs and writes the
wiring block that way.

**Use `allowed_clients`.** A Cognito access token carries `client_id`. It
carries `aud` only when the app client uses a resource binding, and
client-credentials (machine) tokens never do — the first user's own auth
module documents exactly this and checks audience only when present. An
authorizer restricted only by `allowed_audience` therefore rejects machine
callers, and one with no restriction accepts any token the pool signs
(`ACR012`).

**Scopes are fully qualified.** Custom scopes arrive as
`<resource-server-identifier>/<scope>` (for example
`https://mcp.example.test/mcp/records.read`); `allowed_scopes` must use that
form. Per-tool scope checks still belong in the server: the gateway checks
that a scope is present, not which tool it permits.

## Layering with an existing API Gateway authorizer

When the upstream is an API Gateway HTTP API with its own JWT authorizer,
there are two token checks: the gateway's (the user's token) and the upstream
authorizer's (the gateway's outbound token). The second must accept the
gateway's outbound client id in its `audience` list and the handler's allowed
clients (`GWY001`); otherwise every call through the gateway is a 401 that
the gateway reports as a target error.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started-cognito.html,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_gateway
(read 2026-10-05); the first user's authentication notes (private) for the
Cognito `aud` behaviour observed in production.
