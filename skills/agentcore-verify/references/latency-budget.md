# Reading p50/p95 against a budget

The first user's requirement (an Alexa+ add-on) is that a tool call complete
within **500 ms** end to end. `verify.py --samples N --budget-ms 500` measures
it from the machine running the script.

## Percentiles here

Nearest-rank on the sorted samples: p95 of 20 samples is the 19th; of fewer
than 20, effectively the maximum (the report says so). No interpolation, so
every reported number was actually measured. `trace_report.py` uses the same
definition, so the two can be compared.

## What the number includes

| Included | Not included |
|---|---|
| TLS and network round trip from this machine to the gateway's region | the voice platform's own hops |
| gateway authorization, routing and its outbound token fetch | — |
| the upstream (API Gateway + Lambda + DynamoDB/Secrets Manager) | — |

A laptop in another continent can add tens of milliseconds per call that a
client in the same region will not see. Treat the laptop p95 as an upper
bound and confirm with server-side numbers: the gateway's `Latency` and
`TargetExecutionTime` metrics, and X-Ray/Transaction Search traces.

## Splitting the budget

| Hop | Where to read it |
|---|---|
| gateway overhead | gateway span attribute `overhead_latency_ms`, or `Latency` − `TargetExecutionTime` |
| API Gateway (HTTP API) | access log `$context.responseLatency` − `$context.integrationLatency` |
| Lambda init (cold start) | X-Ray `Initialization` subsegment |
| your code | `Invocation` self time |
| DynamoDB / Secrets Manager / HTTP | their subsegments (needs ADOT or a tracer) |

## Sample sizes

20 calls is the minimum for a p95 that means anything; 100 is better. Run
some after an idle period to include cold starts, or the p95 will flatter the
budget. Do not run sustained load from this script: it is a probe, and the
gateway's tool-call rate (200 TPS, shared across the account) is a quota.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-gateway-metrics.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html,
https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html (read 2026-10-05).
