# ---------------------------------------------------------------------------
# THE ONLY CHANGES TO THE SHARED (PRODUCTION) COGNITO USER POOL.
#
# The pool itself is read through a data source and never managed here. This
# module ADDS, inside that pool:
#   1. one resource server  https://alexa.bookshelf.example/mcp  (new identifier),
#   2. one authorization-code + PKCE app client for Alexa+ account linking,
#   3. one client-credentials app client (AgentCore Gateway outbound
#      credential via AgentCore Identity, and the operator's probes).
# Nothing existing in the pool (users, the Google provider, the production
# resource server, its clients, the custom domain) is modified. Destroying this
# environment removes exactly these three objects.
# ---------------------------------------------------------------------------

data "aws_cognito_user_pools" "production" {
  name = var.user_pool_name
}

locals {
  user_pool_id = one(data.aws_cognito_user_pools.production.ids)
  issuer       = "https://cognito-idp.${var.region}.amazonaws.com/${local.user_pool_id}"

  alexa_scope_names = ["mcp:service", "mcp:tools", "mcp:resources"]
  vault_scope_names = [
    "categories.read",
    "categories.write",
    "records.read",
    "records.write",
    "records.delete",
    "records.export",
  ]
  qualified = { for scope in concat(local.alexa_scope_names, local.vault_scope_names) : scope => "${var.resource_identifier}/${scope}" }

  # What Alexa+ may ask a user to consent to: the voice tools need these three
  # vault scopes (see apps/mcp-server/src/profile.ts), plus the Alexa names in
  # case Alexa requests mcp:tools / mcp:resources (with AUTH_FACADE=rewrite).
  alexa_client_scopes = [
    local.qualified["categories.read"],
    local.qualified["records.read"],
    local.qualified["records.write"],
    local.qualified["mcp:tools"],
    local.qualified["mcp:resources"],
  ]
}

resource "aws_cognito_resource_server" "alexa" {
  identifier   = var.resource_identifier
  name         = "Bookshelf Vault Alexa+ (hackathon)"
  user_pool_id = local.user_pool_id

  dynamic "scope" {
    for_each = toset(concat(local.alexa_scope_names, local.vault_scope_names))
    content {
      scope_name        = scope.value
      scope_description = "Bookshelf Vault Alexa ${replace(replace(scope.value, ".", " "), ":", " ")}"
    }
  }
}

# Alexa+ account linking: confidential client (Alexa holds the secret, entered
# with `alexa-ai configure-account-linking`), authorization code + PKCE (S256).
resource "aws_cognito_user_pool_client" "alexa" {
  name                                 = "${var.name}-alexa-plus"
  user_pool_id                         = local.user_pool_id
  generate_secret                      = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = local.alexa_client_scopes
  # Alexa's redirect URLs, plus a loopback URL for the operator's test token
  # (scripts/local/user-token.mjs). Drop test_redirect_urls after the hackathon.
  callback_urls                        = concat(var.alexa_redirect_urls, var.test_redirect_urls)
  supported_identity_providers         = var.identity_providers
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

  depends_on = [aws_cognito_resource_server.alexa]
}

# Service principal: `mcp:service` only — it can discover and list tools, it
# cannot read or write anybody's vault (no vault scope). The AgentCore Gateway
# uses it as its outbound credential and forwards the end user's own token.
resource "aws_cognito_user_pool_client" "service" {
  name                                 = "${var.name}-service"
  user_pool_id                         = local.user_pool_id
  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = [local.qualified["mcp:service"]]
  supported_identity_providers         = ["COGNITO"]
  enable_token_revocation              = true
  access_token_validity                = 60

  token_validity_units {
    access_token = "minutes"
  }

  depends_on = [aws_cognito_resource_server.alexa]
}
