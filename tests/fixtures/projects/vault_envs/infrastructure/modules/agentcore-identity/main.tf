# AgentCore Identity: the OAuth2 credential provider the gateway uses for its
# outbound calls to the vault (client credentials against Cognito).
# Generated with the agentcore plugin (agentcore-identity, recipe
# cognito-m2m-outbound) and adapted: the Cognito client is created in
# modules/alexa-identity (one service client, as briefed), so this module
# receives its id and secret instead of creating a second client.
#
# Write-only arguments keep the secret out of THIS resource's state; the
# secret still exists in the Cognito client's state (aws_cognito_user_pool_client
# exposes client_secret), so the state bucket stays the sensitive store it is.

resource "aws_bedrockagentcore_oauth2_credential_provider" "cognito" {
  name                       = "${var.name}-cognito"
  credential_provider_vendor = "CustomOauth2"

  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id_wo                  = var.client_id
      client_secret_wo              = var.client_secret
      client_credentials_wo_version = var.client_credentials_version

      oauth_discovery {
        discovery_url = var.discovery_url
      }
    }
  }
}
