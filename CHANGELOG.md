# Changelog

## 0.2.0 — 2026-10-05

Every friction logged during the plugin's first real-world use on an Alexa+
MCP server (friction log rows F01–F20) that concerns this plugin is resolved
below; F01 and F03 were shared with the `mcp-server` plugin. Each fix has a
regression test in `tests/skills/test_friction_regressions.py` (named
`test_fNN_*`), replayed on `tests/fixtures/projects/vault_envs`, an anonymised
copy of that user's Terraform (two Terragrunt environments and every module
they call).

| # | Friction | Resolution |
|---|---|---|
| F01 | `discover.py` closed on `0 error(s)…` under two "Missing" gaps | **Fixed.** `summary` counts gaps (`summary.gaps`) and the closing line says "N gap(s)". |
| F03 | scripts left `__pycache__` in the plugin | **Fixed.** `sys.dont_write_bytecode = True` in every script (hygiene-tested), in the test conftest, and pytest runs with `-p no:cacheprovider`. |
| F13 | `gateway_plan.py --with-identity --out-dir DIR` dropped the identity module | **Fixed.** `--out-dir` is the modules directory: `DIR/agentcore-gateway`, `DIR/agentcore-identity` and `DIR/agentcore-gateway-interceptor` are written side by side (the 0.1.0 code wrote identity to `DIR/../agentcore-identity`). When `--with-identity` cannot apply (outbound not oauth, Lambda upstream) the script says so (`GWY015`) instead of silently skipping. |
| F14 | observability names were fixed strings | **Fixed.** Every delivery source/destination and the log group carry `${var.name}` (`/aws/vendedlogs/bedrock-agentcore/${var.name}/<label>`); `tracing_plan.py --name` sets the default (else the gateway's literal name, else the project). |
| F15 | the interceptor GWY002/IDN006 recommend could not be generated | **Fixed.** `gateway_plan.py --interceptor forward-jwt` generates the REQUEST interceptor that copies the caller's already-validated JWT into `params._meta[--meta-key]` (the upstream re-verifies it; no shared secret); `--interceptor signed-claim` signs a short-lived HS256 claim with a Secrets Manager key instead; `--interceptor <lambda arn>` wires an existing one. Generated: `agentcore-gateway-interceptor/` (`src/index.mjs`, role with basic execution + X-Ray, log group, `nodejs22.x` arm64 function via `archive_file`, output `function_arn`), and in the gateway module `interceptor_configuration { interception_points = ["REQUEST"], interceptor { lambda { arn } }, input_configuration { pass_request_headers = true } }` plus `lambda:InvokeFunction` for the gateway role and the module wiring. The handler strips a client-supplied key before setting it and logs nothing (tested under Node when available). `identity-propagation.md` documents option C (forward the JWT) next to C′ (signed claim), and what the upstream must verify; GWY002 / IDN006 point at the flag. Whether the gateway preserves `params._meta` for MCP-server targets is undocumented — `GWY017` and the reference say to prove it after the first apply. |
| F16 | `review.py` did not follow `../../modules`; `.` mixed environments; ACR044 ignored an in-repo X-Ray emitter | **Fixed.** The Terraform reader follows local module sources (including `//` subdirectories) from outside the root; `review.py --env infrastructure/live/<env>` (alias `--root`) reviews one environment and its modules while still scanning code from the project. ACR044 (and `tracing_plan.py`'s OBS013) accept `tracing_config Active` plus code that reads `_X_AMZN_TRACE_ID` / `AWS_XRAY_DAEMON_ADDRESS`. MCP backends are now resolved per module directory (two modules' `aws_lambda_function.mcp` no longer collide) and through REST API integrations (`/mcp` or `{proxy+}` resources). |
| F17 | `deploy_plan.py --root` reported production's provider facts and hard-coded the plugin path | **Fixed.** Stages, quotas, region, the hashicorp/aws constraint (root's own `required_providers`) and the lock (root's own `.terraform.lock.hcl`, "not locked yet" before init) all come from the chosen root; `DPL008` notes a root with no constraint. Commands use `$AGENTCORE_PLUGIN`, set by a printed `setup` line from `CLAUDE_PLUGIN_ROOT`. |
| F18 | the generated gateway role tripped the plugin's own ACR022 | **Fixed.** The role is scoped to the resource types the Service Authorization Reference lists: `workload-identity-directory/*` and `token-vault/*` in this account and region, plus the exact credential-provider ARN, and only the token action the outbound type needs. Generated modules review without ACR022 (tested for oauth and api_key). |
| F19 | the M2M recipe always created a client; the state comment overstated write-only | **Fixed.** `--client-ref aws_cognito_user_pool_client.x` (identity_plan.py and gateway_plan.py) reuses an existing confidential client through `client_id` / `client_secret` (sensitive) inputs and prints the wiring; a non-confidential or non-`client_credentials` client is `IDN007`. The comment now says write-only keeps the secret out of the provider resource's state while the Cognito client resource still stores it. |
| F20 | GWY014 printed for MCP targets; both profiles counted | **Fixed.** `tool_names.py --target-type mcp|lambda|openapi` (GWY014 only for Lambda, or phrased conditionally without a type); a probe report (`discovered.tool_names`) or `tools/list` JSON decides which tools count, code only supplies their locations. |

Also, from the independent review:

- `inbound-jwt-cognito.md`: the `AUTHENTICATE_ONLY` row said "used with token
  passthrough". The AgentCore inbound-auth page (re-read 2026-10-05) says it
  verifies a SigV4 signature, makes no authorization decision, and that
  passthrough "is not available with `AUTHENTICATE_ONLY`". The outbound-auth
  page still says the opposite; the plugin follows the inbound-auth page and
  records the conflict. Corrected in `inbound-jwt-cognito.md`,
  `target-types.md`, `glossary.md`, `review-checklist.md`,
  `identity-propagation.md` and ACR014's message and fix; `JWT_PASSTHROUGH`
  (HTTP and Runtime targets only) and on-behalf-of exchange are now recorded.
- The maintainer's verified-facts ledger (`.dev/`, not shipped): every **V** row names its source as a full URL (the
  `DG/…`, "same blog" and "provider docs (main)" short names are gone); the
  gateway-role IAM resource types moved from **U** to **V**.

New finding ids: `GWY015`, `GWY016`, `GWY017`, `IDN007`, `DPL008`. Tests: 654 → 701.

## 0.1.0 — 2026-10-05

First release.
