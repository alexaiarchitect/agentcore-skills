# AgentCore observability

## Transaction Search (once per account and region)

```bash
aws logs put-resource-policy --policy-name AgentCoreTransactionSearch --policy-document '<allows xray.amazonaws.com logs:PutLogEvents on aws/spans:* and /aws/application-signals/data:*, with aws:SourceArn/aws:SourceAccount conditions>'
aws xray update-trace-segment-destination --destination CloudWatchLogs
aws xray update-indexing-rule --name "Default" --rule '{"Probabilistic": {"DesiredSamplingPercentage": 100}}'
```

The generated `transaction-search.sh` fills in the account, region and
partition. "You must have CloudWatch Transaction Search enabled before you
can enable tracing" for AgentCore resources.

## Gateway, Memory, Identity, Runtime: vended logs and spans

Each resource gets delivery sources for `APPLICATION_LOGS` and `TRACES`,
destinations, and deliveries — in Terraform,
`aws_cloudwatch_log_delivery_source` (`log_type`, `resource_arn`),
`aws_cloudwatch_log_delivery_destination` (a log group, or
`delivery_destination_type = "XRAY"` for traces) and
`aws_cloudwatch_log_delivery`. Gateway spans land in the `aws/spans` log
group.

## What the gateway emits

Metrics in `AWS/Bedrock-AgentCore`: `Invocations`, `Throttles`,
`SystemErrors`, `UserErrors`, `Latency` (time to first response token),
`Duration`, `TargetExecutionTime` (time spent in the target), and
`TargetType`. Spans: a `SERVER` span per operation (tool, gateway, request id,
trace and span id) and a `CLIENT` span per target call (target type,
execution time). Attributes include `gateway.id`, `tool.name`, `latency_ms`,
`overhead_latency_ms`, `jsonrpc.error.code`, `http.response.status_code`.
`overhead_latency_ms` is the gateway's own share — the first number to read
against a budget.

## Agents on Runtime

Add `aws-opentelemetry-distro` and start the process under
`opentelemetry-instrument`; Runtime supplies the rest. For agents outside
Runtime, set (from the guide): `AGENT_OBSERVABILITY_ENABLED=true`,
`OTEL_PYTHON_DISTRO=aws_distro`, `OTEL_PYTHON_CONFIGURATOR=aws_configurator`,
`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_TRACES_EXPORTER=otlp`,
`OTEL_LOGS_EXPORTER=otlp`, `OTEL_METRICS_EXPORTER=awsemf`, plus
`OTEL_RESOURCE_ATTRIBUTES` and the `x-aws-log-group` headers, and
`AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT=true` to keep content out.

## Where to look

The CloudWatch **GenAI Observability** page shows agents, sessions, traces and
the gateway; Transaction Search queries the same spans.

## AgentCore Evaluations (not latency)

Evaluations (generally available since 2026-03-31; available in eu-central-1
and us-east-1) score agent quality with LLM-as-a-judge over the same
OpenTelemetry/OpenInference traces (Strands, LangGraph; TypeScript frameworks
since September 2026). Built-in evaluators are billed per token ($0.0024 per
1,000 input, $0.012 per 1,000 output). It needs the tracing above; it does not
measure time.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-gateway-metrics.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html,
https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available,
https://aws.amazon.com/bedrock/agentcore/pricing/ (read or listed 2026-10-05).
