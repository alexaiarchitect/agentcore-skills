resource "aws_iam_role" "mcp" {
  name = "${var.name}-mcp"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "mcp" {
  name = "${var.name}-mcp"
  role = aws_iam_role.mcp.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Table"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
        Resource = [var.table_arn]
      },
      { Sid = "Secrets", Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = var.secrets_arn },
    ]
  })
}

resource "aws_lambda_function" "mcp" {
  function_name = "${var.name}-mcp"
  filename      = var.artifact_path
  role          = aws_iam_role.mcp.arn
  handler       = "index.handler"
  runtime       = "nodejs24.x"
  architectures = ["arm64"]
  timeout       = 29
  memory_size   = 1024

  tracing_config { mode = "PassThrough" }
}

resource "aws_lambda_function" "worker" {
  function_name = "${var.name}-worker"
  filename      = var.artifact_path
  role          = aws_iam_role.mcp.arn
  handler       = "index.handler"
  runtime       = "nodejs24.x"
  architectures = ["arm64"]
}

resource "aws_apigatewayv2_api" "mcp" {
  name          = var.name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "mcp" {
  api_id                 = aws_apigatewayv2_api.mcp.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.mcp.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.mcp.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name}-cognito"
  jwt_configuration {
    audience = var.client_ids
    issuer   = var.issuer
  }
}

resource "aws_apigatewayv2_route" "public" {
  for_each  = toset(["GET /health", "GET /.well-known/oauth-protected-resource/mcp"])
  api_id    = aws_apigatewayv2_api.mcp.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.mcp.id}"
}

resource "aws_apigatewayv2_route" "mcp" {
  api_id             = aws_apigatewayv2_api.mcp.id
  route_key          = "POST /mcp"
  target             = "integrations/${aws_apigatewayv2_integration.mcp.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

resource "aws_apigatewayv2_domain_name" "mcp" {
  domain_name = var.mcp_domain
  domain_name_configuration {
    certificate_arn = var.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}
