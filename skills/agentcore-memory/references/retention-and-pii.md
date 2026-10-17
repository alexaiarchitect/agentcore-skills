# Retention, keys and personal data

This is engineering guidance, not legal advice; the obligations depend on the
user's jurisdiction and contracts.

## What is kept, and for how long

| Data | Lifetime | Control |
|---|---|---|
| raw events (short-term) | `event_expiry_duration`: 7–365 days | set it to the shortest period the product needs |
| long-term records | until deleted | delete per actor on request |
| event metadata | with the event | **not encrypted with the customer-managed key** — keep personal data out of it |

## Keys

Without `encryption_key_arn` AgentCore uses an AWS-managed key. A
customer-managed KMS key (the generator's default) lets you see every use in
CloudTrail, restrict who can decrypt, and revoke access by disabling the key.
`ACR081` notes a memory without one; `MEM005` warns when personal data is
declared and the key is turned off.

## Erasure

An erasure request means deleting the actor's events (`DeleteEvent`, 20 TPS)
and long-term records in every namespace scoped to that actor. Scoping
namespaces by `{actorId}` is what makes this a bounded operation; a strategy
writing to a shared namespace makes it a search.

## Strategy choice is a data decision

`USER_PREFERENCE` exists to extract facts about a person. Decide whether the
product needs that before enabling it (`MEM007`), and say so in the privacy
notice if it does.

## Quotas (per account and region, checked 2026-10-05)

| Quota | Value |
|---|---|
| memories | 150 (adjustable) |
| strategies per memory | 6 |
| messages per CreateEvent | 100; message 100 KB; event 10 MB |
| CreateEvent | 200 TPS per account; 5 TPS per actor+session with payloads |
| RetrieveMemoryRecords / ListMemoryRecords | 30 TPS each |

## Price (list, checked 2026-10-05)

Short-term memory changes rate card on **2026-10-06**: until then $0.25 per
1,000 new events; from then $1.00 per GB ingested and $0.20 per GB retrieved.
Long-term: $0.75 per 1,000 records per month (built-in), $0.25 (custom, plus
model usage), $0.50 per 1,000 retrievals. `/agentcore:agentcore-cost` applies
the right card for a date.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://aws.amazon.com/bedrock/agentcore/pricing/ (read 2026-10-05).
