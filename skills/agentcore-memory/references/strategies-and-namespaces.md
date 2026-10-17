# Strategies and namespaces

## Built-in strategies

The developer guide lists four built-in strategy types: **semantic**,
**user preference**, **summary** and **episodic**. Each runs some of three
steps: *extraction* (insights from short-term memory become records),
*consolidation* (new record or update an existing one) and *reflection*
(insights across episodes). In Terraform:

| `type` | Extracts | Generated namespace template |
|---|---|---|
| `SEMANTIC` | facts and knowledge | `facts/{actorId}` |
| `SUMMARIZATION` | session summaries | `summaries/{actorId}/{sessionId}` |
| `USER_PREFERENCE` | a person's preferences — personal data | `preferences/{actorId}` |
| `EPISODIC` | episodes, with optional reflection | `episodes/{actorId}` |
| `CUSTOM` | your prompts and model; needs `configuration` | — |

Rules: at most **six** strategies per memory, **one of each built-in type**,
and `namespace_templates` holds **exactly one** template. The generator
writes one strategy per requested built-in type; CUSTOM is refused (`MEM002`)
because its configuration is model- and prompt-specific.

```hcl
resource "aws_bedrockagentcore_memory_strategy" "semantic" {
  name                = "semantic"
  memory_id           = aws_bedrockagentcore_memory.this.id
  type                = "SEMANTIC"
  namespace_templates = ["facts/{actorId}"]
}
```

`description` cannot be removed once set. Recent provider additions:
`namespace_templates` and the `reflection` block for episodic overrides
(6.57.1), `self_managed_configuration` (6.62.0).

## Choosing

- An assistant that should remember what a user told it: `SEMANTIC`, plus
  `USER_PREFERENCE` if it adapts to the person.
- Long conversations that must fit a context window: `SUMMARIZATION`.
- Agents that learn procedures from outcomes: `EPISODIC`.
- Start with one; each strategy multiplies stored records (and their price).

## Price differences

Built-in strategies store records at $0.75 per 1,000 per month; custom or
override strategies at $0.25 per 1,000, plus the model usage they incur in
your account. Retrievals are $0.50 per 1,000. Extraction throughput is capped
at 150,000 tokens per minute for long-term memory (adjustable) and 50,000 per
session for episodic.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-strategies.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory_strategy,
https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md,
https://aws.amazon.com/bedrock/agentcore/pricing/,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html (read 2026-10-05).
