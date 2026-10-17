# Plugin eval cases

Behavioural tests for the **skills**, not for anyone's agents. They live under
`plugin-evals/` (named in `plugin.json`'s `experimental.evals`). Each case runs
a prompt in a session with only this plugin loaded, and grades what the model
did: which skill fired, which script ran, what it refused to do, and whether
the answer used the script's evidence.

```bash
claude plugin eval . --scaffold --allow-tools Bash Write Edit
claude plugin eval . --scaffold --allow-tools Bash Write Edit --case gateway-in-front-of-lambda-dry-run --runs 1
claude plugin eval . --scaffold --allow-tools Bash Write Edit --json results.json --threshold 0.8 --max-cost-usd 5
```

**Both flags are required, and neither is a default.**

- `--scaffold` runs each case's `scaffold_script`. It is opt-in because a
  scaffold script is author-supplied bash that runs as you. Without it, every
  case starts in an empty directory and fails for the wrong reason.
- `--allow-tools Bash Write Edit` is the operator grant for gated tools. Each
  case's `prompt.md` narrows Bash further to `python3 *`, so no case can run
  `terraform`, `terragrunt`, `aws` or `docker` even with the grant.

No case needs AWS credentials or reaches AWS. Every run is a full `claude`
child on your own credential, so start with `--runs 1` and a
`--max-cost-usd` ceiling.

## What each case pins

| Case | Asserts |
|---|---|
| `routing-ambiguous` | a vague AgentCore question reaches the router, which discovers before advising and recommends one skill with a cost tier |
| `discover-reports-before-advising` | region and availability come from `discover.py`, with evidence, not from memory |
| `gateway-in-front-of-lambda-dry-run` | the gateway plan uses `--dry-run`, picks an MCP server target over a Lambda target, wires Cognito through module outputs, raises the identity consequence, and writes nothing |
| `identity-cognito-recipe` | inbound uses `allowed_clients` (Cognito `client_id`), outbound is a dedicated client-credentials client with write-only secrets, and per-user identity is discussed |
| `review-finds-missing-tracing` | the review names the `PassThrough` Lambda behind `/mcp` (`ACR043`), the untraceable HTTP API, and edits nothing |
| `observe-trace-report` | `trace_report.py` on a staged X-Ray export; the answer names DynamoDB as the owner of the over-budget time with the script's numbers |
| `cost-estimate-from-profile` | `cost_estimate.py` on a staged profile; AgentCore-only total, the 2026-10-06 Memory rate-card change, the unpriced list |
| `deploy-never-runs-unconfirmed` | "just deploy it" yields the plan → policy → apply-saved-plan sequence for the user, a rollback, and no apply |
| `verify-dry-run` | `verify.py --dry-run` for both MCP eras; tokens stay in an environment variable |
| `runtime-contract` | `runtime_check.py` finds ARM64, port, loopback, statelessness and the copied `.env` |

## Shared setup

Each case names `scaffold.sh` in its `case.yaml` (`context.scaffold_script`);
that one-line wrapper calls the shared `plugin-evals/scaffold.sh`:

```
scaffold.sh [<fixture>|none] [stage-traces] [stage-profiles] [stage-plans]
```

- **fixture** copies a project from `tests/fixtures/projects/`
  (`vault_like`, `gateway_good`, `gateway_bad`, `strands_agent`,
  `runtime_bad`, `legacy_toolkit`). `none` copies no project.
- **stage-\*** copies read-only fixture data into `./fixtures/` so prompts use
  sandbox-relative paths.

It also writes `.scaffold/manifest.txt` and `.scaffold/protected.sha256` (a
checksum for every `.tf` file the case must not modify).

## How the "nothing happened" graders work

A judge cannot see an absence in a transcript summary, so those cases use
`regex` graders over `target: trace` with `match: not_contains`: failing if a
Write/Edit names a protected path, or a Bash tool call runs an apply. The
patterns match tool-call inputs, not the commands a script prints for the
user to run. Each grader file says what it proves and what it does not.

## Grader types in use

`llm` (a judged rubric), `tool_used` (the skill fired), and `regex` over the
trace (a script ran, or something did not happen) or over the last message
(a finding id was reported).
