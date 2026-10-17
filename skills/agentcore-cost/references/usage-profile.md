# The usage profile

A JSON object. Every section is optional; omit what you do not use. Unknown
top-level keys are refused (a typo should not silently price nothing).

```json
{
  "name": "label for the report",
  "region": "eu-central-1",
  "days_per_month": 30,
  "gateway": {
    "requests_per_day": 2000,
    "tool_calls_per_request": 1,
    "list_calls_per_request": 0.2,
    "other_calls_per_day": 0,
    "search_calls_per_day": 0,
    "tools_indexed": 14
  },
  "identity": {"token_requests_per_day": 2000, "via_runtime_or_gateway": true},
  "runtime": {"sessions_per_day": 500, "avg_session_seconds": 20, "active_cpu_fraction": 0.25,
              "vcpu": 1, "memory_gb": 2, "idle_seconds_after": 0, "compute": "microvm_v2"},
  "memory": {"events_per_day": 4000, "avg_event_kb": 2, "short_term_retrieved_gb_per_month": 0,
             "long_term_records": 5000, "retrievals_per_day": 1000, "strategy": "builtin"},
  "evaluations": {"evaluated_per_day": 50, "input_tokens_per_eval": 2000, "output_tokens_per_eval": 300},
  "model_tokens": {"requests_per_day": 0, "input_tokens_per_request": 0, "output_tokens_per_request": 0,
                   "price_per_1000_input": 0.0, "price_per_1000_output": 0.0},
  "unpriced": ["AWS Lambda", "Amazon API Gateway", "Amazon CloudWatch Logs"]
}
```

## How each field is used

| Field | Formula |
|---|---|
| `gateway.*` | invocations = days × requests × (tool calls + list calls) + days × other calls; × $0.005 / 1,000 |
| `gateway.search_calls_per_day` | days × searches × $0.025 / 1,000 |
| `gateway.tools_indexed` | tools × $0.02 / 100 (monthly) |
| `identity.*` | free when `via_runtime_or_gateway` (the default), else × $0.010 / 1,000 |
| `runtime.*` | vCPU-h = days × sessions × seconds × active fraction × vCPU / 3,600; GB-h = days × sessions × (seconds + idle tail ≤ 120 s) × GB / 3,600 |
| `runtime.compute` | `microvm_v2` (default), `microvm_v2_committed`, `microvm_v1` |
| `memory.events_per_day` | until 2026-10-05: × $0.25 / 1,000; from 2026-10-06: GB = events × KB / 1,048,576, × $1.00 |
| `memory.long_term_records` | stored records × $0.75 (built-in) or $0.25 (`custom`, `override`, `self_managed`) / 1,000 |
| `memory.retrievals_per_day` | days × retrievals × $0.50 / 1,000 |
| `evaluations.*` | days × evaluations × tokens × the built-in token price / 1,000 |
| `model_tokens.*` | only if you supply `price_per_1000_*` |
| `unpriced` | listed in the report; default is Lambda, API Gateway, CloudWatch Logs, X-Ray, DynamoDB |

`--as-of` chooses the Memory rate card (default: today). The estimate never
guesses missing numbers: an absent field is zero unless a default is listed
above (tool calls per request 1, active fraction 1, vCPU 1, memory 2 GB,
session 30 s, event 2 KB, evaluation tokens 2,000/300).

Sources: https://aws.amazon.com/bedrock/agentcore/pricing/ (read 2026-10-05);
this plugin's `lib/agentcore_skills/cost.py`.
