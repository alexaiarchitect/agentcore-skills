output "issuer" { value = "https://${aws_cognito_user_pool.vault.endpoint}" }
output "user_pool_id" { value = aws_cognito_user_pool.vault.id }
output "client_ids" { value = { for name, client in aws_cognito_user_pool_client.public : name => client.id } }
output "authorized_client_ids" {
  value = concat(values(aws_cognito_user_pool_client.public)[*].id, values(aws_cognito_user_pool_client.machine)[*].id)
}
output "machine_client_ids" {
  value = { for name, client in aws_cognito_user_pool_client.machine : name => client.id }
}
output "machine_client_secrets" {
  value     = { for name, client in aws_cognito_user_pool_client.machine : name => client.client_secret }
  sensitive = true
}
output "google_callback_url" { value = "https://${var.auth_domain}/oauth2/idpresponse" }
output "auth_cloudfront_distribution" { value = aws_cognito_user_pool_domain.custom.cloudfront_distribution }
output "authorization_endpoint" { value = "https://${var.auth_domain}/oauth2/authorize" }
output "token_endpoint" { value = "https://${var.auth_domain}/oauth2/token" }
