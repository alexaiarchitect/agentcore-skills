output "oauth_provider_arn" { value = aws_bedrockagentcore_oauth2_credential_provider.cognito.credential_provider_arn }
output "credential_secret_arn" { value = aws_bedrockagentcore_oauth2_credential_provider.cognito.client_secret_arn }
