data "aws_region" "current" {}

locals {
  common_environment = {
    TABLE_NAME               = var.table_name
    EXPORT_BUCKET            = var.export_bucket_name
    EXPORT_QUEUE_URL         = var.export_queue_url
    COGNITO_ISSUER           = var.cognito_issuer
    OAUTH_RESOURCE           = var.oauth_resource
    OAUTH_ALLOWED_CLIENT_IDS = join(",", var.authorized_client_ids)
    SECRETS_ARN              = var.secrets_arn
    SHARING_ENABLED          = var.sharing_enabled ? "true" : "false"
    LOG_LEVEL                = "INFO"
    POWERTOOLS_SERVICE_NAME  = var.name
  }
}

resource "aws_iam_role" "mcp" {
  name = "${var.name}-mcp"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = var.tags
}

resource "aws_iam_role" "worker" {
  name = "${var.name}-export-worker"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = var.tags
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

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.name}"
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
        # ConditionCheckItem is a distinct action from PutItem/UpdateItem and is
        # required for the grant check that guards contributor writes inside the
        # same transaction as the records.
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
      {
        Sid      = "WriteLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.mcp.arn}:*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "worker" {
  name = "${var.name}-export-worker"
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadAndUpdateVault"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [var.table_arn]
      },
      { Sid = "WriteExports", Effect = "Allow", Action = ["s3:PutObject"], Resource = "${var.export_bucket_arn}/exports/*" },
      {
        Sid      = "ConsumeQueue"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = var.export_queue_arn
      },
      {
        Sid      = "WriteLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.worker.arn}:*"
      },
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
  memory_size                    = 1024
  reserved_concurrent_executions = var.mcp_reserved_concurrency

  environment { variables = local.common_environment }
  tracing_config { mode = "PassThrough" }
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
  tracing_config { mode = "PassThrough" }
  tags = var.tags

  depends_on = [aws_iam_role_policy.worker, aws_cloudwatch_log_group.worker]
}

resource "aws_lambda_event_source_mapping" "exports" {
  event_source_arn                   = var.export_queue_arn
  function_name                      = aws_lambda_function.worker.arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_apigatewayv2_api" "mcp" {
  name          = var.name
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "mcp" {
  api_id                 = aws_apigatewayv2_api.mcp.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.mcp.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

# Rejects unsigned and expired tokens before the Lambda is billed. It cannot do
# per-tool scopes, because every tool multiplexes one route, so it is a filter
# and never the authority: the handler still verifies the token itself and must
# never trust claims injected here.
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id                            = aws_apigatewayv2_api.mcp.id
  authorizer_type                   = "JWT"
  identity_sources                  = ["$request.header.Authorization"]
  name                              = "${var.name}-cognito"
  authorizer_payload_format_version = null

  jwt_configuration {
    audience = var.authorized_client_ids
    issuer   = var.cognito_issuer
  }
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = toset([
    "GET /health",
    "GET /ready",
    "GET /.well-known/oauth-protected-resource/mcp",
    "GET /.well-known/oauth-protected-resource",
  ])
  api_id    = aws_apigatewayv2_api.mcp.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.mcp.id}"
}

# Only the tool route is gated; discovery and health must stay reachable so an
# unauthenticated client can learn where to get a token.
resource "aws_apigatewayv2_route" "mcp" {
  api_id             = aws_apigatewayv2_api.mcp.id
  route_key          = "POST /mcp"
  target             = "integrations/${aws_apigatewayv2_integration.mcp.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

resource "aws_apigatewayv2_stage" "production" {
  api_id      = aws_apigatewayv2_api.mcp.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId = "$context.requestId"
      routeKey  = "$context.routeKey"
      status    = "$context.status"
      latency   = "$context.responseLatency"
      sourceIp  = "$context.identity.sourceIp"
    })
  }

  tags = var.tags
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mcp.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.mcp.execution_arn}/*/*"
}

resource "aws_apigatewayv2_domain_name" "mcp" {
  domain_name = var.mcp_domain
  domain_name_configuration {
    certificate_arn = var.mcp_certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
  tags = var.tags
}

resource "aws_apigatewayv2_api_mapping" "mcp" {
  api_id      = aws_apigatewayv2_api.mcp.id
  domain_name = aws_apigatewayv2_domain_name.mcp.id
  stage       = aws_apigatewayv2_stage.production.id
}
