# Sessions, isolation and cold starts

## One microVM per session

"Each session in AgentCore Runtime receives its own dedicated microVM with
isolated compute, memory, and filesystem resources." When the session ends
the microVM is terminated and its memory sanitised. That is the isolation
guarantee — and the cost: a new session is a new microVM.

## Lifecycle

| State | Meaning |
|---|---|
| Active | processing a request, a command or background work |
| Idle | finished, still available for the next invocation |
| Stopped | microVM terminated: idle timeout (default 15 minutes), max lifetime (default 8 hours; up to 14 days on Runtime Instances), `StopRuntimeSession`, or failed health checks |

A stopped session resumes on the next invocation with a **new** microVM and
the same lifecycle configuration. Set them in Terraform with
`lifecycle_configuration { idle_runtime_session_timeout, max_lifetime }`.

## Session ids

"Generate a unique session ID for each user or conversation with at least 33
characters" and pass it on every related call — `runtimeSessionId` in
`InvokeAgentRuntime`, or the protocol's session header. Without a consistent
id, "each request may be routed to a new microVM, which may result in
additional latency due to cold starts."

## State

Memory and disk live only for the microVM's lifetime. For files across
stop/resume, configure session storage (1 GB per session); for conversation
and user state, use AgentCore Memory.

## Cold starts against a latency budget

AWS does not publish a cold-start figure for Runtime, and this plugin does
not invent one. What is documented: a new session provisions a microVM; a
reused session id keeps affinity; CPU is billed only while active and memory
is reclaimed after 120 s idle (microVMs v2). So:

- A **voice** budget (the first user's is 500 ms end to end) leaves little
  room for a first-call microVM start. Measure first-call and warm-call
  latency separately with `verify.py --samples` on a fresh and a reused
  session before committing a voice path to Runtime.
- A stateless MCP tool server already meeting its budget on Lambda gains
  nothing from Runtime on the hot path; front it with a gateway instead.
- New-session creation is throttled at 25 TPS per account (adjustable), so a
  burst of new users is also a quota question.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://aws.amazon.com/bedrock/agentcore/pricing/,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime (read 2026-10-05).
