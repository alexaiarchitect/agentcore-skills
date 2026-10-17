# Every planted defect here is named by the test that expects it.
provider "aws" {
  region = "eu-central-1"
}

variable "upstream_api_token" {
  type = string
}

resource "aws_iam_role_policy" "gateway_admin" {
  name = "too-broad"
  role = "gateway"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }]
  })
}

resource "aws_iam_role_policy" "lambda_star" {
  name = "lambda-star"
  role = "gateway"
  policy = <<EOT
{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Action": ["lambda:*"], "Resource": "*"}]
}
EOT
}

resource "aws_bedrockagentcore_gateway" "open" {
  name            = "open-gateway"
  role_arn        = "arn:aws:iam::111122223333:role/gateway"
  authorizer_type = "NONE"
  protocol_type   = "MCP"
}

resource "aws_bedrockagentcore_gateway" "loose" {
  name            = "loose-gateway"
  role_arn        = "arn:aws:iam::111122223333:role/gateway"
  authorizer_type = "CUSTOM_JWT"
  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url = "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_EXAMPLE"
    }
  }
  protocol_type = "MCP"
  protocol_configuration {
    mcp {
      supported_versions = ["2025-11-25", "2024-11-05"]
      search_type        = "SEMANTIC"
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "plain_http" {
  name               = "upstream"
  gateway_identifier = aws_bedrockagentcore_gateway.loose.gateway_id
  target_configuration {
    mcp {
      mcp_server {
        endpoint     = "http://internal.example.test/mcp"
        listing_mode = "DYNAMIC"
      }
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "lambda_oauth" {
  name               = "tools"
  gateway_identifier = aws_bedrockagentcore_gateway.loose.gateway_id
  credential_provider_configuration {
    oauth {
      provider_arn = "arn:aws:bedrock-agentcore:eu-central-1:111122223333:token-vault/default/oauth2credentialprovider/x"
      scopes       = []
    }
  }
  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.tools.arn
        tool_schema {
          inline_payload {
            name        = "lookup"
            description = "Look something up"
            input_schema {
              type = "object"
            }
          }
        }
      }
    }
  }
}

resource "aws_lambda_function" "tools" {
  function_name = "tools"
  role          = "arn:aws:iam::111122223333:role/tools"
  handler       = "index.handler"
  runtime       = "nodejs24.x"
  filename      = "tools.zip"
}

resource "aws_bedrockagentcore_api_key_credential_provider" "literal" {
  name    = "upstream-key"
  api_key = "sk-live-0123456789abcdef"
}

resource "aws_bedrockagentcore_memory" "too_long" {
  name                  = "too_long"
  event_expiry_duration = 400
}

resource "aws_bedrockagentcore_registry" "catalog" {
  name = "catalog"
}
