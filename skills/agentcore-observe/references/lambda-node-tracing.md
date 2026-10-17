# Tracing a Node.js 24 Lambda

## Turn on active tracing

```hcl
resource "aws_lambda_function" "mcp" {
  # ...
  tracing_config { mode = "Active" }   # was PassThrough: Lambda never started a segment
}

resource "aws_iam_role_policy_attachment" "xray" {
  role       = aws_iam_role.mcp.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}
```

With `PassThrough`, Lambda only propagates a trace header it received; with an
HTTP API in front (which never sends one), no trace exists at all.

## Instrument downstream calls: ADOT (recommended)

The AWS Lambda Layer for OpenTelemetry (ADOT JavaScript) auto-instruments the
AWS SDK and HTTP, so DynamoDB, Secrets Manager and outbound HTTP become
subsegments without code changes:

```hcl
  layers = ["arn:aws:lambda:eu-central-1:615299751070:layer:AWSOpenTelemetryDistroJs:28"]
  environment {
    variables = { AWS_LAMBDA_EXEC_WRAPPER = "/opt/otel-instrument" }
  }
```

Layer versions checked 2026-10-05: **28 in eu-central-1, 31 in us-east-1**;
look up the current one in the ADOT layer table before applying. The ADOT
docs say the JavaScript layer supports Node.js 18+ runtimes, and the Lambda
Node.js tracing page's layer example lists `nodejs24.x`; confirm on a dev
stage that subsegments appear. CloudWatch Application Signals documents
`CloudWatchLambdaApplicationSignalsExecutionRolePolicy` for the role and calls
active tracing optional but recommended.

The older community layer (`aws-otel-nodejs-<arch>-ver-1-30-2`) uses
`AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-handler`; do not mix the two wrappers.

## ESM and bundlers

The ADOT JavaScript layer hot-patches the handler at runtime. With `esbuild`,
the ADOT docs require exporting the handler via `module.exports` rather than
`export`, because an ESM `export` binding is immutable. A pure-ESM bundle
(`"type": "module"`, as the first user's package is) needs checking: either
emit a CommonJS handler shim for the wrapper to patch, or instrument in code
(below) instead of through the wrapper. Test in a dev stage before relying on
it: a wrapper that cannot patch fails silently — the function runs, the
subsegments never appear (`OBS005`).

## Alternative: Powertools Tracer or the X-Ray SDK in code

`@aws-lambda-powertools/tracer` (the project already uses Powertools logger
and metrics) wraps the AWS SDK clients and adds annotations such as
`cold_start` and the tool name. The X-Ray SDKs (`aws-xray-sdk-core`) entered
maintenance mode on 2026-02-25 with end of support on 2027-02-25; AWS
recommends migrating to OpenTelemetry, so prefer ADOT for anything new.

## What to annotate

Tool name, MCP method and protocol revision as annotations (indexed,
filterable) — never arguments or results. With those, `get-trace-summaries`
can filter `annotation.tool = "query_records"`.

Sources: https://docs.aws.amazon.com/lambda/latest/dg/nodejs-tracing.html,
https://aws-otel.github.io/docs/getting-started/lambda,
https://aws-otel.github.io/docs/getting-started/lambda/lambda-js,
https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html,
https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-eos.html (read 2026-10-05).
