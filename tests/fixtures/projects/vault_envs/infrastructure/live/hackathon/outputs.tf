output "mcp_endpoint" {
  description = "The Alexa+ add-on MCP endpoint (direct). Use this in addon.json and alexa-ai new mcp --mcp-server-url."
  value       = local.oauth_resource
}
output "health_endpoint" { value = "https://${var.domain}/health" }
output "authorization_server_metadata" { value = "https://${var.domain}/.well-known/oauth-authorization-server" }
output "cognito_issuer" { value = module.identity.issuer }
output "token_endpoint" { value = "https://${var.auth_domain}/oauth2/token" }
output "alexa_client_id" { value = module.identity.alexa_client_id }
output "alexa_client_secret" {
  value     = module.identity.alexa_client_secret
  sensitive = true
}
output "service_client_id" { value = module.identity.service_client_id }
output "service_client_secret" {
  value     = module.identity.service_client_secret
  sensitive = true
}
output "service_scope" { value = module.identity.service_scope }
output "gateway_url" {
  description = "AgentCore Gateway MCP URL: optional experiment only, NOT the add-on endpoint."
  value       = module.agentcore_gateway.gateway_url
}
output "gateway_id" { value = module.agentcore_gateway.gateway_id }
output "rest_api_id" { value = module.compute.rest_api_id }
output "mcp_lambda_name" { value = module.compute.mcp_lambda_name }
