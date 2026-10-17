---
name: agentcore-identity
description: >-
  Configure Amazon Bedrock AgentCore Identity in both directions. Inbound:
  Amazon Cognito (or any OIDC issuer) trusted by a gateway or runtime through
  `custom_jwt_authorizer` — discovery URL, `allowed_clients` on `client_id`,
  fully-qualified scopes. Outbound: credential providers in the token vault —
  an OAuth2 provider (`CustomOauth2` pointed at Cognito's discovery URL, with
  a confidential client-credentials app client and write-only secrets), an API
  key provider, or a standalone workload identity — plus the
  `@requires_access_token` / `@requires_api_key` decorators for agent code.
  Reads the project's pools, clients and resource servers, reports `IDN0xx`
  findings, writes a Terraform module after a dry run and prints the
  `aws bedrock-agentcore-control` equivalents. Also covers the hard part:
  whether the end user's identity survives the hop through a gateway. Use when
  asked "Cognito with AgentCore", "inbound auth for the gateway", "outbound
  OAuth to my API", "client credentials for the gateway", "credential
  provider", "token vault", "workload identity", "requires_access_token",
  "will my server still know which user called". Don't use for putting the
  gateway itself in place (use `/agentcore:agentcore-gateway`), for IAM
  breadth (use `/agentcore:agentcore-review`), or for Cognito user-pool design
  unrelated to AgentCore.
argument-hint: "[project-dir] --recipe cognito-inbound|cognito-m2m-outbound|api-key-outbound|workload-identity"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# AgentCore Identity: who calls, and who the upstream thinks called

Inbound and outbound identity are configured in different places and fail in
different ways. Inbound lives on the gateway or runtime (a JWT authorizer;
nothing to create in AgentCore Identity). Outbound lives in AgentCore
Identity (a credential provider the gateway or agent draws a token from). The
question users forget to ask is the third one: once a request crosses the
gateway with the gateway's credential, does the upstream still know which
user it is for?

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Discover** the pools, clients and resource servers:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../agentcore-discover/scripts/discover.py <project> --focus auth,region
   ```

2. **Plan a recipe**, read-only:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/identity_plan.py <project> --recipe cognito-m2m-outbound --scopes records.read --dry-run
   ```

   Recipes: `cognito-inbound` (what to pass to an authorizer),
   `cognito-m2m-outbound` (client + OAuth2 provider; `--client-ref
   aws_cognito_user_pool_client.x` reuses an existing confidential client),
   `api-key-outbound`, `workload-identity`. Each prints its CLI equivalent.

3. **Report** the `IDN` findings. When the upstream derives ownership from
   the token subject (the first user's server does: owner =
   hash(issuer, sub)), go through
   [identity-propagation.md](references/identity-propagation.md) with the user
   before writing anything: client credentials make every user the same
   principal.

4. **Options** (all free to generate): the recipe as planned; a different
   propagation design; the CLI equivalents only. **Confirm** with
   `AskUserQuestion`, then write.

5. **Verify** with `review.py`; after deploy, `verify.py` with a real user
   token proves the inbound side, and the upstream's logs prove the outbound
   side.

## The `IDN0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `IDN001` | warn | no Cognito pool in the project; `user_pool_id` becomes a variable |
| `IDN002` | info | Cognito access tokens carry `client_id`, `aud` only with a resource binding |
| `IDN003` | info | custom scopes are fully qualified in tokens |
| `IDN004` | info | client-credentials clients already exist; the recipe adds a dedicated one |
| `IDN005` | warn | client credentials without a resource-server scope |
| `IDN006` | warn | the outbound token identifies the gateway, not the end user |
| `IDN007` | warn | `--client-ref` names a client that is not a confidential client-credentials client |

## Decision rules

- **Secrets are write-only or not at all.** `client_secret_wo` /
  `api_key_wo` with a version counter; never a literal (`ACR030`), never a
  plain argument that lands in state (`ACR031`).
- **One dedicated outbound client per gateway.** Reusing an end-to-end test
  client makes logs ambiguous and couples rotation.
- **Identity through Runtime or Gateway is free.** Token and API-key requests
  cost $0.010 per 1,000 only when made outside them.

## References

| Question | File |
|---|---|
| Inbound vs outbound, workload identity, token vault, decorators | [inbound-outbound-model.md](references/inbound-outbound-model.md) |
| The Cognito recipes in full, with CLI equivalents | [cognito-recipes.md](references/cognito-recipes.md) |
| OAuth2 vendors, API keys, grant types, write-only arguments | [credential-providers.md](references/credential-providers.md) |
| Keeping the end user's identity across the gateway | [identity-propagation.md](references/identity-propagation.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/identity_plan.py <project> --recipe R [--scopes a,b] [--client-ref ADDR] [--dry-run] [--force] [--json]` | `IDN` findings, the module, CLI equivalents | 0 planned/written, 1 error finding, 2 bad arguments |

## Completion checklist

- [ ] Discovery's auth block was shown: pools, clients (with flows), resource servers.
- [ ] Inbound uses `allowed_clients`; scopes are in fully qualified form.
- [ ] Outbound secrets are write-only; no secret was written to a file.
- [ ] The identity-propagation consequence was discussed and the user chose a design.
- [ ] The write plan was confirmed before writing, and `review.py` re-run.
