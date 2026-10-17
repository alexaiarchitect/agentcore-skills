# AgentCore pricing dimensions

List prices from the AgentCore pricing page, read **2026-10-05**. The page
publishes one rate card for commercial regions (its examples name US East);
it does not list per-region rates, so treat these as estimates and check the
page for eu-central-1 before committing.

| Service | Dimension | Price |
|---|---|---|
| Runtime (microVMs v2, consumption) | vCPU-hour | $0.1276 |
| | GB-hour | $0.0169 |
| | billing | per second, 1-second minimum; CPU scales to zero during I/O wait; memory reclaimed after 120 s idle |
| Runtime (microVMs v2, committed baseline, launching October 2026) | vCPU-hour / GB-hour | $0.0997 / $0.0132 |
| Runtime (microVMs v1) | vCPU-hour / GB-hour | $0.0895 / $0.00945 |
| Runtime Instances | — | EC2 price plus a management fee (12% standard, 7.8% GPU) |
| Gateway | API invocations (ListTools, InvokeTool, Ping…) | $0.005 per 1,000 |
| | search API | $0.025 per 1,000 |
| | tool indexing | $0.02 per 100 tools per month |
| Identity | token or API-key requests | $0.010 per 1,000 — **no charge through Runtime or Gateway** |
| Memory, short-term | until 2026-10-05 | $0.25 per 1,000 new events |
| | from 2026-10-06 | $1.00 per GB ingested; $0.20 per GB retrieved |
| Memory, long-term | records, built-in strategy | $0.75 per 1,000 per month |
| | records, custom/override strategy | $0.25 per 1,000 per month + model usage in your account |
| | retrievals | $0.50 per 1,000 |
| Code Interpreter, Browser | vCPU-hour / GB-hour | $0.0895 / $0.00945 |
| Evaluations (built-in) | input / output tokens | $0.0024 / $0.012 per 1,000 |
| Policy | authorization request | $0.000025 |
| Observability | — | CloudWatch prices |
| Optimization (Insights) | — | free in public preview |

Free tier: "New AWS customers receive up to $200 in Free Tier credits" — an
account-level credit, not an AgentCore allowance.

## What the first user's design pays for

A gateway in front of an existing Lambda MCP server, with an outbound
credential and no Runtime: Gateway invocations (every `tools/list` and
`tools/call`, plus pings), tool indexing for 14 tools, and nothing for
Identity (used through the gateway). At 2,000 requests a day with 1.2
gateway calls each, that is 72,000 invocations, about **$0.36 per month**,
plus $0.003 for indexing. The Lambda, API Gateway, CloudWatch and X-Ray costs
it already pays continue, and Transaction Search indexing at 100% sampling
adds to CloudWatch.

## Not priced by this plugin

Lambda, API Gateway, CloudWatch Logs and metrics, X-Ray/Transaction Search,
DynamoDB, Secrets Manager, ECR, KMS, data transfer, and Bedrock model
inference. Add them from their own pricing pages.

Sources: https://aws.amazon.com/bedrock/agentcore/pricing/ (read 2026-10-05).
