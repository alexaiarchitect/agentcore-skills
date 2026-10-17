resource "aws_cognito_user_pool" "users" {
  name                = "${var.name}-users"
  deletion_protection = "ACTIVE"
}

resource "aws_cognito_resource_server" "api" {
  identifier   = "https://mcp.example-vault.test/mcp"
  name         = "Example Vault MCP"
  user_pool_id = aws_cognito_user_pool.users.id
  scope {
    scope_name        = "records.read"
    scope_description = "read records"
  }
}

resource "aws_cognito_user_pool_client" "public" {
  for_each                             = { assistant = var.callback_urls }
  name                                 = "${var.name}-${each.key}"
  user_pool_id                         = aws_cognito_user_pool.users.id
  generate_secret                      = false
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "https://mcp.example-vault.test/mcp/records.read"]
  callback_urls                        = each.value
}

resource "aws_cognito_user_pool_client" "machine" {
  for_each                             = toset(["e2e"])
  name                                 = "${var.name}-m2m-${each.key}"
  user_pool_id                         = aws_cognito_user_pool.users.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["https://mcp.example-vault.test/mcp/records.read"]
}
