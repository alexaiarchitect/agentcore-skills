# Runbook: where did the time go?

## 0. Prerequisites (once)

- Lambda on the request path: `tracing_config { mode = "Active" }`, X-Ray
  write permission, the ADOT layer (see `lambda-node-tracing.md`).
- Transaction Search enabled in the account and region
  (`transaction-search.sh`), sampling at 100% while measuring.
- AgentCore gateway (and runtime, memory) TRACES delivery to X-Ray.

## 1. Find slow requests

Set the window and the service name (the Lambda function name is the X-Ray
service name for Lambda segments):

```bash
export AWS_REGION=eu-central-1 SERVICE=example-vault-mcp
START=$(date -u -d '-1 hour' +%s 2>/dev/null || date -u -v-1H +%s); END=$(date -u +%s)

# everything over 500 ms
aws xray get-trace-summaries --region $AWS_REGION --start-time $START --end-time $END \
  --filter-expression "service(\"$SERVICE\") AND responsetime > 0.5" > slow-summaries.json

# all requests (for the distribution)
aws xray get-trace-summaries --region $AWS_REGION --start-time $START --end-time $END \
  --filter-expression "service(\"$SERVICE\")" > all-summaries.json

# cold starts only
aws xray get-trace-summaries --region $AWS_REGION --start-time $START --end-time $END \
  --filter-expression "service(\"$SERVICE\") AND annotation.cold_start = true" > cold.json  # if you annotate
```

Other useful filters: `responsetime > 0.5 AND !fault`, `service("DynamoDB")
{ responsetime > 0.1 }`, `http.url CONTAINS "/mcp"`.

## 2. Fetch the full segment trees

`batch-get-traces` takes at most 5 trace ids per call:

```bash
python3 -c 'import json;ids=[t["Id"] for t in json.load(open("all-summaries.json"))["TraceSummaries"]];[print(" ".join(ids[i:i+5])) for i in range(0,len(ids),5)]' \
| while read -r batch; do aws xray batch-get-traces --region $AWS_REGION --trace-ids $batch; done \
| python3 -c 'import json,sys;d=json.JSONDecoder();s=sys.stdin.read();o=[];i=0
while i<len(s):
  s2=s[i:].lstrip();
  if not s2: break
  v,n=d.raw_decode(s2);o+=v["Traces"];i=len(s)-len(s2)+n
print(json.dumps({"Traces":o}))' > traces.json
```

For AgentCore spans (gateway, runtime) and ADOT spans, export the `aws/spans`
log group instead (CloudWatch Logs Insights, or `aws logs filter-log-events
--log-group-name aws/spans ... --output json` and keep the `message` of each
event, one JSON span per line). `trace_report.py` reads both.

## 3. Summarise

```bash
python3 <plugin>/skills/agentcore-observe/scripts/trace_report.py traces.json --budget-ms 500
```

Read, in order: total p50/p95 and how many traces were over budget; the
"over-budget owners" (mean self time per segment in the slow requests only);
the segments table sorted by self p95; cold-start share.

## 4. Typical answers and fixes

| Owner of the time | Usual cause | Fix |
|---|---|---|
| `Initialization` | Lambda cold start (bundle size, init work) | smaller bundle, lazy init, provisioned concurrency for the voice path |
| `DynamoDB` | a scan, a hot partition, or a cross-region table | query by key, check the access pattern, keep the table in-region |
| `SecretsManager` | fetching a secret per invocation | cache it for the container lifetime |
| `Invocation` self time | your code (JSON Schema compile, crypto) | profile; cache compiled schemas |
| gateway span self time / `overhead_latency_ms` | gateway auth + outbound token fetch | reuse sessions (2025 era); check the outbound provider is in-region |
| API Gateway (from access log) | integration latency vs response latency gap | rarely large; check throttling |

## 5. Prove the fix

Re-run `verify.py --samples 20 --budget-ms 500`, export the new window,
re-run `trace_report.py`, and compare the same rows.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-gateway-metrics.html,
https://docs.aws.amazon.com/lambda/latest/dg/nodejs-tracing.html,
https://docs.aws.amazon.com/xray/latest/devguide/xray-services-apigateway.html (read 2026-10-05). The
`get-trace-summaries`/`batch-get-traces` command shapes and filter-expression grammar are X-Ray's
standard API and were not re-read for this plugin; check `aws xray get-trace-summaries help`.
