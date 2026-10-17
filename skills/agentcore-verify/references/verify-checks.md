# What each check proves

| Check | Proves | Does not prove |
|---|---|---|
| `initialize` returns `Mcp-Session-Id` (2025 era) | the gateway accepted the token and serves that revision | anything about the upstream |
| `tools/list` returns the expected `<target>___<tool>` names | targets are synchronised and the gateway reached the catalogue | that a call reaches the upstream with valid credentials |
| one `tools/call` succeeds | outbound credential, upstream auth and the tool path all work for this token | per-user identity (see below) |
| repeated calls, p50/p95 ≤ budget | the end-to-end latency from this machine | where the time goes (traces) |
| `--protocol both`, equal tool lists | both revisions are served and translate | elicitation/sampling across revisions (not translated) |
| `/ping` `Healthy` from a local container | the image meets the HTTP health contract | that the deployed runtime is healthy |

## Getting a token for the test

For a Cognito machine client (client credentials), from the pool's token
endpoint — the user runs this; the secret stays in their shell:

```bash
export GATEWAY_TOKEN="$(curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d grant_type=client_credentials -d scope="$SCOPE" \
  "https://$COGNITO_DOMAIN/oauth2/token" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')"
```

The client must be in the gateway's `allowed_clients`. For a human-user test,
use a token from the real client's authorization-code flow.

## AWS-side checks (`aws_checks.py`)

All read-only; the user runs them:

- `aws bedrock-agentcore-control get-gateway` — status, URL, supported
  versions, authorizer type;
- `list-gateway-targets` — each target's status (an OAuth target can rest in
  `CREATE_PENDING_AUTH` until authorised);
- `list-oauth2-credential-providers`, `list-api-key-credential-providers`,
  `list-workload-identities` — the identity pieces exist;
- `aws xray get-trace-summaries --filter-expression 'service("<fn>") AND
  responsetime > 0.5'` — server-side requests over budget in the window;
- `aws cloudwatch get-metric-statistics --namespace AWS/Bedrock-AgentCore
  --metric-name Latency --extended-statistics p50 p95` — the gateway's own
  latency (list dimensions first);
- `aws bedrock-agentcore invoke-agent-runtime` — a runtime smoke call.

The control-plane command names follow the AgentCore API operation names
(`GetGateway`, `ListGatewayTargets`, `ListOauth2CredentialProviders`, …); the
`create-oauth2-credential-provider` form is shown verbatim in the AgentCore
Cognito guide. Confirm the others with `aws bedrock-agentcore-control help`.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-sessions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started-cognito.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-gateway-metrics.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html (read 2026-10-05).
