locals {
  # Human sign-in needs an identity provider; until Google credentials exist the
  # pool still works for machine-to-machine clients, which need no provider.
  identity_providers = var.google_client_id == "" ? ["COGNITO"] : [for provider in aws_cognito_identity_provider.google : provider.provider_name]

  scope_names = [
    "categories.read",
    "categories.write",
    "records.read",
    "records.write",
    "records.delete",
    "records.export",
    "shares.read",
    "shares.write",
  ]
  oauth_scopes = concat(["openid", "email", "profile"], [for scope in local.scope_names : "${var.resource_identifier}/${scope}"])
}

resource "aws_cognito_user_pool" "vault" {
  name                = "${var.name}-users"
  deletion_protection = "ACTIVE"
  mfa_configuration   = "OFF"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = var.tags
}

resource "aws_cognito_resource_server" "vault" {
  identifier   = var.resource_identifier
  name         = "Bookshelf Vault MCP"
  user_pool_id = aws_cognito_user_pool.vault.id

  dynamic "scope" {
    for_each = toset(local.scope_names)
    content {
      scope_name        = scope.value
      scope_description = "Bookshelf Vault ${replace(scope.value, ".", " ")} permission"
    }
  }
}

resource "aws_cognito_identity_provider" "google" {
  count         = var.google_client_id == "" ? 0 : 1
  user_pool_id  = aws_cognito_user_pool.vault.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    authorize_scopes = "openid email profile"
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
  }

  attribute_mapping = {
    email          = "email"
    email_verified = "email_verified"
    username       = "sub"
    given_name     = "given_name"
    family_name    = "family_name"
  }
}

resource "aws_cognito_user_pool_domain" "custom" {
  domain          = var.auth_domain
  certificate_arn = var.auth_certificate_arn
  user_pool_id    = aws_cognito_user_pool.vault.id
}

resource "aws_cognito_user_pool_client" "public" {
  for_each = {
    chatgpt = var.chatgpt_callback_urls
    desktop = var.desktop_callback_urls
    test    = var.test_callback_urls
  }

  name                                 = "${var.name}-${each.key}"
  user_pool_id                         = aws_cognito_user_pool.vault.id
  generate_secret                      = false
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = local.oauth_scopes
  callback_urls                        = each.value
  supported_identity_providers         = local.identity_providers
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  access_token_validity                = 60
  id_token_validity                    = 60
  refresh_token_validity               = 30
  auth_session_validity                = 3

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  depends_on = [aws_cognito_resource_server.vault]
}

# Machine-to-machine principals used by the end-to-end suite. Client credentials
# is the only OAuth flow that can be scripted, and each client is a distinct
# principal because owner identity derives from the token subject.
resource "aws_cognito_user_pool_client" "machine" {
  for_each = toset(["owner", "recipient"])

  name                                 = "${var.name}-m2m-${each.key}"
  user_pool_id                         = aws_cognito_user_pool.vault.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = [for scope in local.scope_names : "${var.resource_identifier}/${scope}"]
  supported_identity_providers         = ["COGNITO"]
  enable_token_revocation              = true
  access_token_validity                = 60
  token_validity_units {
    access_token = "minutes"
  }

  depends_on = [aws_cognito_resource_server.vault]
}
