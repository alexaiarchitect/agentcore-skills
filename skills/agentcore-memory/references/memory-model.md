# The Memory model

## Short-term and long-term

- **Short-term memory** "stores raw interactions that help the agent maintain
  context within a single session." Each user turn and agent reply is an
  **event** (or a batch of them). Events can be conversational or structured
  (product details, order status), and since August 2026 non-conversational
  JSON payloads can be stored and extracted too.
- **Long-term memory** records "store structured information extracted from
  raw agent interactions, which is retained across multiple sessions" — only
  the key insights: summaries, facts, preferences. Strategies do the
  extraction; content can also be ingested directly into long-term memory
  (August 2026).

## Identifiers

Events are written per **actor** (the end user, or the agent acting for one)
and **session** (`sessionId`, yours or generated). Strategies place extracted
records under **namespaces** built from templates that can include the actor
and session, which is what scopes retrieval.

## Expiry

`event_expiry_duration` (Terraform) is in **days**, 7 to 365. It governs raw
events. Long-term records live until deleted.

## Terraform

```hcl
resource "aws_bedrockagentcore_memory" "this" {
  name                  = "library_memory"
  event_expiry_duration = 30
  encryption_key_arn    = aws_kms_key.memory.arn   # omit for an AWS-managed key
  # memory_execution_role_arn: "IAM role ARN for memory service operations" (e.g. custom strategies)
}
```

Exported: `arn`, `id`. Strategies are separate
`aws_bedrockagentcore_memory_strategy` resources referencing `memory_id`.

## Using it from an agent

The AgentCore Python SDK's `MemoryClient` (`bedrock_agentcore.memory`)
creates events and retrieves records; discovery reports any file that
imports it. The data-plane calls are rate-limited per actor and session (5
CreateEvent TPS with payloads), so batch turns rather than writing one event
per token.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html (read 2026-10-05).
