# Capability map

What each skill does, what it reads, what it can write, and what it costs.
Scripts are standard-library Python 3.10+; none imports an AWS SDK.

| Skill | Reads | Writes (after confirmation) | Emits for you to run | Tier |
|---|---|---|---|---|
| `agentcore-discover` | Terraform, code, Dockerfiles, manifests | nothing | nothing | free |
| `agentcore-create` | the project | a Terraform module (runtime, gateway, identity, memory), or a CDK stack | AgentCore CLI commands (`--iac cli`) | free |
| `agentcore-review` | Terraform, code, Dockerfiles | nothing | nothing | free |
| `agentcore-gateway` | routes, Lambdas, Cognito, MCP server code | gateway module (+ identity module) | wiring block | free |
| `agentcore-identity` | Cognito pools, clients, resource servers | identity module | `aws bedrock-agentcore-control` equivalents | free |
| `agentcore-runtime` | Dockerfile, entry points, routes | Dockerfile, `.dockerignore` | `docker buildx` | free |
| `agentcore-memory` | memories in Terraform, SDK usage | memory module | nothing | free |
| `agentcore-deploy` | the whole Terraform tree | nothing | init/validate/plan/show/apply, rollback | aws |
| `agentcore-verify` | a gateway URL + token you provide; a local `/ping` | nothing | read-only `aws` checks | aws |
| `agentcore-observe` | Terraform; an exported trace file | observability module, Lambda tracing patch, Transaction Search script | `aws xray` queries | free |
| `agentcore-cost` | a usage profile; Terraform for budgets | budget module | nothing | free |
| `agentcore-ci` | Terraform, existing workflows | a plan-only workflow + vendored checker | nothing | free |

## Typical sequences

**An MCP server on Lambda, adding a gateway (the first user's case):**
discover → gateway (dry run, then write) → identity (outbound recipe) →
review → observe (tracing plan) → cost → deploy (plan, policy, apply by the
user) → verify (both MCP revisions, p95 vs budget) → observe (trace report).

**An agent to host on Runtime:** discover → runtime (contract check,
Dockerfile) → create (runtime module) → memory → review → deploy → verify.

**An existing AgentCore estate:** discover → review → ci.

## What needs the user's AWS credentials

Only the commands the deploy, verify and observe skills print. The plugin's
scripts never read AWS credentials and never make an AWS API call; the only
network access is `verify.py` calling the gateway URL (or local `/ping`) the
user names, with the token from the environment variable they name.

Sources: this plugin's scripts; AgentCore developer guide,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/ (read 2026-10-05).
