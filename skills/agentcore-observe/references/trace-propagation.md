# Trace context across the hops

## Headers AgentCore documents

| Header | Purpose | Example |
|---|---|---|
| `X-Amzn-Trace-Id` | X-Ray trace context | `Root=1-5759e988-bd862e3fe1be46a994272793;Parent=53995c3f42cd8ad8;Sampled=1` |
| `traceparent` | W3C trace context | `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` |
| `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` | Runtime session | a ≥ 33-character id |
| `baggage` | propagated key-values | `userId=alice,serverRegion=us-east-1` |

## The first user's path, hop by hop

```
client ──► AgentCore Gateway ──► API Gateway (HTTP API) ──► Lambda (MCP) ──► DynamoDB / Secrets Manager
          SERVER + CLIENT spans   no X-Ray segment            segment (Active)   subsegments (ADOT)
```

1. **Client → Gateway.** A client that sends `traceparent` or
   `X-Amzn-Trace-Id` lets its own trace continue; most MCP clients send
   nothing, so the gateway's `SERVER` span starts the trace.
2. **Gateway → upstream.** The gateway's `CLIENT` span covers the target
   call. Whether the gateway forwards a trace header to an MCP server target
   (so the Lambda segment joins the same trace) is **not documented** on the
   pages read for this plugin. Check empirically: after a call through the
   gateway, look up the gateway's trace id in Transaction Search and see
   whether the Lambda segment appears under it.
3. **API Gateway HTTP API.** Not X-Ray traced. It passes headers through to
   the Lambda integration, but with no segment of its own.
4. **Lambda.** With `Active` tracing Lambda records a segment for every
   sampled invocation; with `PassThrough` it only propagates a header it
   received. (Continuation of an incoming `X-Amzn-Trace-Id` is X-Ray's general
   Lambda behaviour, not re-read for this plugin.)
5. **Downstream.** ADOT/Powertools add subsegments for AWS SDK and HTTP calls.

## If the traces do not join

Correlate instead of joining: the gateway span carries `aws.request.id` and
the tool name; log the incoming `X-Amzn-Trace-Id`/`traceparent` and the MCP
request id in the Lambda (Powertools logger does the former), and match on
time window plus tool name. `trace_report.py` can read each side separately;
the gateway's `TargetExecutionTime` minus the Lambda's total is the network
and API Gateway share.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-gateway-metrics.html,
https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html,
https://docs.aws.amazon.com/lambda/latest/dg/nodejs-tracing.html (read 2026-10-05).
