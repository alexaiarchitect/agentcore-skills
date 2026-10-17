output "user_pool_id" { value = local.user_pool_id }
output "issuer" { value = local.issuer }
output "discovery_url" { value = "${local.issuer}/.well-known/openid-configuration" }
output "resource_server_identifier" { value = aws_cognito_resource_server.alexa.identifier }
output "alexa_client_id" { value = aws_cognito_user_pool_client.alexa.id }
output "alexa_client_secret" {
  value     = aws_cognito_user_pool_client.alexa.client_secret
  sensitive = true
}
output "service_client_id" { value = aws_cognito_user_pool_client.service.id }
output "service_client_secret" {
  value     = aws_cognito_user_pool_client.service.client_secret
  sensitive = true
}
output "service_scope" { value = local.qualified["mcp:service"] }
