# The AgentCore Identity model

## Two directions

| | Inbound | Outbound |
|---|---|---|
| Question | who may call this gateway/runtime? | what does the gateway/agent present upstream? |
| Configured on | the gateway or runtime (`authorizer_type`, `custom_jwt_authorizer`) | AgentCore Identity (credential providers) + the target's `credential_provider_configuration`, or a decorator in agent code |
| Created in AgentCore Identity | nothing | an OAuth2 or API key credential provider |
| Fails as | 401 at the gateway | 401/403 from the upstream, reported by the gateway as a target error |

## Terms (from the AgentCore Identity terminology page)

- **Workload identity** — "a logical application or workload that is
  independent of specific hardware or infrastructure"; agent identities are a
  specialised kind. A gateway gets one automatically when created; so does a
  runtime. Create one yourself only for an agent hosted elsewhere
  (`aws_bedrockagentcore_workload_identity`, with the allowed OAuth return
  URLs for 3LO flows).
- **Token vault** — "secure storage for OAuth 2.0 tokens, API keys, and other
  credentials… credentials can only be accessed by the specific agent and
  user combination that originally obtained them."
- **Resource credential provider** — the component that runs OAuth flows and
  retrieves credentials from an external identity provider.
- **Agent access token** — an AWS-signed token carrying both the workload
  identity and the user identity, produced by token exchange.

## Decorators in agent code (Python SDK)

```python
from bedrock_agentcore.identity.auth import requires_access_token, requires_api_key

@requires_access_token(provider_name="vault-cognito", scopes=["records.read"], auth_flow="M2M")
async def call_vault(*, access_token: str): ...

@requires_access_token(provider_name="google-provider",
                       scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"],
                       auth_flow="USER_FEDERATION", on_auth_url=print,
                       callback_url="<oauth2 callback url for session binding>")
async def read_drive(*, access_token: str): ...
```

`auth_flow` is `"M2M"` (client credentials) or `"USER_FEDERATION"` (3LO);
`force_authentication=False` lets a cached token be reused. Inside Runtime
the workload access token is obtained for you; outside it, the
`GetWorkloadAccessToken*` APIs (200 TPS quota each) supply it.

## Quotas (per account and region, checked 2026-10-05)

Workload identities 11,000; OAuth2 credential providers 50; API key providers
50 (all adjustable). Token APIs 200 TPS; `CompleteResourceTokenAuth` 100 TPS;
CRUD APIs 20 TPS.

## Pricing

$0.010 per 1,000 token or API-key requests — at no additional charge when
used through AgentCore Runtime or AgentCore Gateway.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-terminology.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-authentication.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-create.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://aws.amazon.com/bedrock/agentcore/pricing/,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_workload_identity (read 2026-10-05).
