# A gateway in front of an existing MCP endpoint, configured the way this
# plugin recommends. The review of this fixture must come back clean.
terraform {
  required_version = ">= 1.11"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.55.0"
    }
  }
  backend "s3" {
    bucket       = "example-state"
    key          = "gateway/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-central-1"
}

data "aws_caller_identity" "current" {}

variable "outbound_client_id" {
  type      = string
  sensitive = true
}

variable "outbound_client_secret" {
  type      = string
  sensitive = true
}

resource "aws_iam_role" "gateway" {
  name = "example-gateway"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "gateway" {
  name = "example-gateway"
  role = aws_iam_role.gateway.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_bedrockagentcore_oauth2_credential_provider.cognito.client_secret_arn]
    }]
  })
}

resource "aws_bedrockagentcore_oauth2_credential_provider" "cognito" {
  name                       = "example-cognito"
  credential_provider_vendor = "CustomOauth2"
  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id_wo                  = var.outbound_client_id
      client_secret_wo              = var.outbound_client_secret
      client_credentials_wo_version = 1
      oauth_discovery {
        discovery_url = "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_EXAMPLE/.well-known/openid-configuration"
      }
    }
  }
}

resource "aws_bedrockagentcore_gateway" "main" {
  name            = "example-gateway"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "CUSTOM_JWT"
  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_EXAMPLE/.well-known/openid-configuration"
      allowed_clients = ["exampleclientid1"]
    }
  }
  protocol_type = "MCP"
  protocol_configuration {
    mcp {
      supported_versions = ["2025-11-25", "2026-07-28"]
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "vault" {
  name               = "vault"
  gateway_identifier = aws_bedrockagentcore_gateway.main.gateway_id
  credential_provider_configuration {
    oauth {
      provider_arn = aws_bedrockagentcore_oauth2_credential_provider.cognito.credential_provider_arn
      scopes       = ["https://mcp.example-vault.test/mcp/records.read"]
    }
  }
  target_configuration {
    mcp {
      mcp_server {
        endpoint     = "https://mcp.example-vault.test/mcp"
        listing_mode = "DEFAULT"
      }
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "transaction_search" {
  policy_name = "TransactionSearchXRayAccess"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "xray.amazonaws.com" }
      Action    = "logs:PutLogEvents"
      Resource  = ["arn:aws:logs:eu-central-1:111122223333:log-group:aws/spans:*"]
    }]
  })
}

resource "aws_cloudwatch_log_delivery_source" "gateway_logs" {
  name         = "gateway-logs"
  log_type     = "APPLICATION_LOGS"
  resource_arn = aws_bedrockagentcore_gateway.main.gateway_arn
}

resource "aws_cloudwatch_log_delivery_source" "gateway_traces" {
  name         = "gateway-traces"
  log_type     = "TRACES"
  resource_arn = aws_bedrockagentcore_gateway.main.gateway_arn
}
