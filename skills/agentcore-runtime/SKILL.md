---
name: agentcore-runtime
description: >-
  Host an agent or an MCP server on Amazon Bedrock AgentCore Runtime and check
  it against the container contract before the first deploy: an ARM64 image
  listening on 0.0.0.0, HTTP on 8080 with POST `/invocations` and GET `/ping`
  (`Healthy` / `HealthyBusy`), MCP on 8000 at `/mcp` with stateless Streamable
  HTTP that accepts the platform's `Mcp-Session-Id`, A2A on 9000; no `.env`
  in the image, a non-root user, ADOT (`opentelemetry-instrument`) for
  AgentCore observability. Explains session semantics (one microVM per
  session, 15-minute idle and 8-hour lifetime defaults, session ids of at
  least 33 characters, state lost on stop unless session storage or Memory is
  used) and what that means for cold starts against a latency budget.
  Generates a contract-correct Dockerfile; findings are the `RTM0xx` band.
  Use when asked "host my agent on AgentCore", "run my MCP server on
  Runtime", "write the Dockerfile for AgentCore", "why does my runtime fail
  health checks", "what is the /ping contract", "AgentCore cold start",
  "session id". Don't use for the Runtime Terraform resource alone (use
  `/agentcore:agentcore-create --component runtime`), for a gateway (use
  `/agentcore:agentcore-gateway`), or for Lambda hosting.
argument-hint: "[project-dir] [--protocol HTTP|MCP]"
allowed-tools: Read, Grep, Glob, Write, Edit, AskUserQuestion, Skill, Bash(python3 *)
---

# Hosting on AgentCore Runtime

Runtime starts a fresh microVM for every session from your image and talks to
it on a fixed contract. A container that runs fine with `docker run` on an
x86 laptop can fail its first invocation on Runtime for three boring reasons
— wrong architecture, wrong port, no `/ping` — and this skill catches them
from the files.

`${CLAUDE_SKILL_DIR}` is set by the skill runtime to this skill's own
directory. Use it verbatim in every command below; a sibling skill's scripts
are at `${CLAUDE_SKILL_DIR}/../<skill>/scripts/`.

## Flow

1. **Check the contract.**

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/runtime_check.py <project>
   ```

   The protocol comes from the Terraform runtime resource if there is one,
   else from the code (an MCP server without an agent entry point is `MCP`).
   Force it with `--protocol HTTP|MCP|A2A|AGUI`.

2. **Report** errors first (`RTM001` ARM64, `RTM007` `.env` in the image —
   rotate what it held), then the contract warnings, then notes. Always
   repeat `RTM010`: sessions and cold starts decide whether Runtime fits a
   tight latency budget at all.

3. **Options:** generate a Dockerfile (free), fix the code (free), scaffold
   the runtime resource with `/agentcore:agentcore-create --component runtime`
   (free), or plan the deploy (`/agentcore:agentcore-deploy`, aws).

4. **Confirm** with `AskUserQuestion`, then generate:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gen_dockerfile.py <project> --protocol MCP --entry server.py --dry-run
   ```

5. **Verify** by re-running `runtime_check.py`; after a local
   `docker run -p 8080:8080`, `verify.py --ping-url http://localhost:8080/ping`.

## The `RTM0xx` band

| Id | Severity | Trigger |
|---|---|---|
| `RTM001` | **error** | the image does not target `linux/arm64` |
| `RTM002` | warn | `EXPOSE` lacks the protocol's port |
| `RTM003` | warn | HTTP protocol, no `GET /ping` |
| `RTM004` | warn | HTTP protocol, no `POST /invocations` |
| `RTM005` | warn | MCP protocol, no `/mcp` endpoint |
| `RTM006` | warn | Python MCP server without `stateless_http=True` |
| `RTM007` | **error** | `.env` copied into the image |
| `RTM008` | info | runs as root |
| `RTM009` | info | no ADOT instrumentation |
| `RTM010` | info | sessions and cold starts (always reported) |
| `RTM011` | warn | binds to loopback instead of 0.0.0.0 |

## Decision rules

- **ARM64 or nothing.** Build with `docker buildx build --platform
  linux/arm64`; an x86 image will not start.
- **Stateless MCP.** The platform generates `Mcp-Session-Id` and sends it;
  the server must accept, not reject, a session id it did not issue.
- **Reuse the session id.** Every call in a conversation carries the same id
  (≥ 33 characters), or each may land on a new microVM and pay a cold start.
- **Runtime is not Lambda.** For a stateless tool server already on Lambda,
  keep Lambda and front it with a gateway; move to Runtime for agents that
  need sessions, long runs (up to 8 hours) or isolation per user.

## References

| Question | File |
|---|---|
| Ports, paths, `/ping` format, headers, per protocol | [container-contract.md](references/container-contract.md) |
| Session lifecycle, isolation, persistence, cold starts vs a budget | [sessions-and-cold-start.md](references/sessions-and-cold-start.md) |
| Build, push, deploy, invoke; quotas | [deploy-and-invoke.md](references/deploy-and-invoke.md) |

## Scripts

| Command | Does | Exit codes |
|---|---|---|
| `scripts/runtime_check.py <project> [--protocol P] [--json]` | the `RTM0xx` check | 0 no errors, 1 errors, 2 nothing to check |
| `scripts/gen_dockerfile.py <project> [--protocol HTTP\|MCP] [--language python\|node] [--entry F] [--dry-run] [--force] [--json]` | a contract-correct Dockerfile and `.dockerignore` | 0 written/planned, 1 nothing, 2 bad arguments |

## Completion checklist

- [ ] `runtime_check.py` ran and the protocol it inferred was confirmed with the user.
- [ ] ARM64, port, `/ping` (HTTP) or stateless `/mcp` (MCP) were each confirmed or fixed.
- [ ] Session and cold-start behaviour was explained against the user's latency budget.
- [ ] Generated files were shown as a write plan first; `runtime_check.py` re-run clean.
