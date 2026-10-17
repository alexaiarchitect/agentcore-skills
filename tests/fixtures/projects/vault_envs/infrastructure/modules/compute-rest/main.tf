# Compute for the Alexa+ hackathon environment: the same two Lambdas as
# production plus the AgentCore Gateway interceptor, behind an API Gateway
# REST API (v1). REST, not HTTP API, because only REST APIs can emit an X-Ray
# segment; with Lambda `Active` tracing and the in-code subsegments (DynamoDB,
# SQS, S3, Secrets Manager, Cognito) one trace covers
#   AgentCore Gateway -> API Gateway -> Lambda -> AWS services.

data "aws_region" "current" {}

locals {
  common_environment = merge({
    TABLE_NAME               = var.table_name
    EXPORT_BUCKET            = var.export_bucket_name
    EXPORT_QUEUE_URL         = var.export_queue_url
    COGNITO_ISSUER           = var.cognito_issuer
    OAUTH_RESOURCE           = var.oauth_resource
    OAUTH_ALLOWED_CLIENT_IDS = join(",", var.authorized_client_ids)
    SECRETS_ARN              = var.secrets_arn
    SHARING_ENABLED          = "false"
    LOG_LEVEL                = "INFO"
    POWERTOOLS_SERVICE_NAME  = var.name
  }, var.extra_environment)
  lambda_trust = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role" "mcp" {
  name               = "${var.name}-mcp"
  assume_role_policy = local.lambda_trust
  tags               = var.tags
}

resource "aws_iam_role" "worker" {
  name               = "${var.name}-export-worker"
  assume_role_policy = local.lambda_trust
  tags               = var.tags
}

resource "aws_iam_role" "interceptor" {
  name               = "${var.name}-gateway-interceptor"
  assume_role_policy = local.lambda_trust
  tags               = var.tags
}

# X-Ray write access for Active tracing and the in-code subsegments.
resource "aws_iam_role_policy_attachment" "xray" {
  for_each   = { mcp = aws_iam_role.mcp.name, worker = aws_iam_role.worker.name, interceptor = aws_iam_role.interceptor.name }
  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

resource "aws_cloudwatch_log_group" "mcp" {
  name              = "/aws/lambda/${var.name}-mcp"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.name}-export-worker"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "interceptor" {
  name              = "/aws/lambda/${var.name}-gateway-interceptor"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_iam_role_policy" "mcp" {
  name = "${var.name}-mcp"
  role = aws_iam_role.mcp.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VaultTable"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:ConditionCheckItem",
          "dynamodb:TransactWriteItems"
        ]
        Resource = [var.table_arn]
      },
      { Sid = "QueueExports", Effect = "Allow", Action = ["sqs:SendMessage"], Resource = var.export_queue_arn },
      { Sid = "ReadSecrets", Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = var.secrets_arn },
      { Sid = "DownloadExports", Effect = "Allow", Action = ["s3:GetObject"], Resource = "${var.export_bucket_arn}/exports/*" },
      { Sid = "WriteLogs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.mcp.arn}:*" },
    ]
  })
}

resource "aws_iam_role_policy" "worker" {
  name = "${var.name}-export-worker"
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "ReadAndUpdateVault", Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"], Resource = [var.table_arn] },
      { Sid = "WriteExports", Effect = "Allow", Action = ["s3:PutObject"], Resource = "${var.export_bucket_arn}/exports/*" },
      { Sid = "ConsumeQueue", Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = var.export_queue_arn },
      { Sid = "WriteLogs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.worker.arn}:*" },
    ]
  })
}

resource "aws_iam_role_policy" "interceptor" {
  name = "${var.name}-gateway-interceptor"
  role = aws_iam_role.interceptor.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "WriteLogs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.interceptor.arn}:*" },
    ]
  })
}

resource "aws_lambda_function" "mcp" {
  function_name                  = "${var.name}-mcp"
  filename                       = var.mcp_artifact_path
  source_code_hash               = filebase64sha256(var.mcp_artifact_path)
  role                           = aws_iam_role.mcp.arn
  handler                        = "index.handler"
  runtime                        = "nodejs24.x"
  architectures                  = ["arm64"]
  timeout                        = 29
  memory_size                    = var.mcp_memory_mb
  reserved_concurrent_executions = var.mcp_reserved_concurrency

  environment { variables = local.common_environment }
  # Active: Lambda starts the function segment and exposes the daemon address
  # the in-code subsegments are sent to (packages/observability/src/xray.ts).
  tracing_config { mode = "Active" }
  tags = var.tags

  depends_on = [aws_iam_role_policy.mcp, aws_cloudwatch_log_group.mcp]
}

resource "aws_lambda_function" "worker" {
  function_name                  = "${var.name}-export-worker"
  filename                       = var.worker_artifact_path
  source_code_hash               = filebase64sha256(var.worker_artifact_path)
  role                           = aws_iam_role.worker.arn
  handler                        = "index.handler"
  runtime                        = "nodejs24.x"
  architectures                  = ["arm64"]
  timeout                        = 300
  memory_size                    = 1024
  reserved_concurrent_executions = var.worker_reserved_concurrency

  environment { variables = local.common_environment }
  tracing_config { mode = "Active" }
  tags = var.tags

  depends_on = [aws_iam_role_policy.worker, aws_cloudwatch_log_group.worker]
}

resource "aws_lambda_function" "interceptor" {
  function_name    = "${var.name}-gateway-interceptor"
  filename         = var.interceptor_artifact_path
  source_code_hash = filebase64sha256(var.interceptor_artifact_path)
  role             = aws_iam_role.interceptor.arn
  handler          = "index.handler"
  runtime          = "nodejs24.x"
  architectures    = ["arm64"]
  timeout          = 5
  memory_size      = 256

  tracing_config { mode = "Active" }
  tags = var.tags

  depends_on = [aws_iam_role_policy.interceptor, aws_cloudwatch_log_group.interceptor]
}

resource "aws_lambda_event_source_mapping" "exports" {
  event_source_arn                   = var.export_queue_arn
  function_name                      = aws_lambda_function.worker.arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

# ---- REST API (v1) --------------------------------------------------------

resource "aws_api_gateway_rest_api" "mcp" {
  name                         = var.name
  description                  = "Bookshelf Vault MCP for Alexa+ (hackathon)"
  disable_execute_api_endpoint = true
  # Lets the function return the store-listing PNGs (isBase64Encoded). Request
  # bodies then arrive base64-encoded too; the handler decodes them.
  binary_media_types = ["*/*"]
  endpoint_configuration { types = ["REGIONAL"] }
  tags = var.tags
}

# One greedy proxy resource plus the root: the Lambda owns routing, as in
# production. No API-level authorizer: the function verifies every token
# itself and must answer 401 without WWW-Authenticate for Alexa+, which a
# Cognito authorizer's own 401 would not guarantee.
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.mcp.id
  parent_id   = aws_api_gateway_rest_api.mcp.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" {
  rest_api_id   = aws_api_gateway_rest_api.mcp.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy" {
  rest_api_id             = aws_api_gateway_rest_api.mcp.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.mcp.invoke_arn
  timeout_milliseconds    = 29000
}

resource "aws_api_gateway_deployment" "mcp" {
  rest_api_id = aws_api_gateway_rest_api.mcp.id
  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy.id,
      aws_api_gateway_integration.proxy.id,
    ]))
  }
  lifecycle { create_before_destroy = true }
}

resource "aws_api_gateway_stage" "mcp" {
  rest_api_id          = aws_api_gateway_rest_api.mcp.id
  deployment_id        = aws_api_gateway_deployment.mcp.id
  stage_name           = var.stage_name
  xray_tracing_enabled = true

  # Access logs need the account-level API Gateway CloudWatch role, which this
  # environment does not manage (it is account-wide). Enable only if
  # `aws apigateway get-account` already shows a cloudwatchRoleArn.
  dynamic "access_log_settings" {
    for_each = var.enable_access_logs ? [1] : []
    content {
      destination_arn = aws_cloudwatch_log_group.api[0].arn
      format = jsonencode({
        requestId           = "$context.requestId"
        resourcePath        = "$context.resourcePath"
        status              = "$context.status"
        responseLatency     = "$context.responseLatency"
        integrationLatency  = "$context.integrationLatency"
        xrayTraceId         = "$context.xrayTraceId"
        sourceIp            = "$context.identity.sourceIp"
      })
    }
  }
  tags = var.tags
}

resource "aws_cloudwatch_log_group" "api" {
  count             = var.enable_access_logs ? 1 : 0
  name              = "/aws/apigateway/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.mcp.id
  stage_name  = aws_api_gateway_stage.mcp.stage_name
  method_path = "*/*"
  settings {
    throttling_burst_limit = var.throttle_burst
    throttling_rate_limit  = var.throttle_rate
    metrics_enabled        = true
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowRestApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mcp.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.mcp.execution_arn}/*/*"
}

resource "aws_api_gateway_domain_name" "mcp" {
  domain_name              = var.domain
  regional_certificate_arn = var.certificate_arn
  security_policy          = "TLS_1_2"
  endpoint_configuration { types = ["REGIONAL"] }
  tags = var.tags
}

resource "aws_api_gateway_base_path_mapping" "mcp" {
  api_id      = aws_api_gateway_rest_api.mcp.id
  stage_name  = aws_api_gateway_stage.mcp.stage_name
  domain_name = aws_api_gateway_domain_name.mcp.domain_name
}
