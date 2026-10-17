output "mcp_endpoint" { value = local.oauth_resource }
output "health_endpoint" { value = "https://${var.mcp_domain}/health" }
output "oauth_issuer" { value = module.identity.issuer }
output "oauth_authorization_endpoint" { value = module.identity.authorization_endpoint }
output "oauth_token_endpoint" { value = module.identity.token_endpoint }
output "google_callback_url" { value = module.identity.google_callback_url }
output "oauth_client_ids" { value = module.identity.client_ids }
output "github_deploy_role_arn" { value = module.github_oidc.deploy_role_arn }
output "dashboard_name" { value = module.observability.dashboard_name }

output "machine_client_ids" { value = module.identity.machine_client_ids }
output "machine_client_secrets" {
  value     = module.identity.machine_client_secrets
  sensitive = true
}
output "token_endpoint" { value = module.identity.token_endpoint }
output "cognito_issuer" { value = module.identity.issuer }
