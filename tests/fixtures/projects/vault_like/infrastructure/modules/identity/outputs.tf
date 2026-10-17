output "issuer" { value = "https://${aws_cognito_user_pool.users.endpoint}" }
output "user_pool_id" { value = aws_cognito_user_pool.users.id }
output "authorized_client_ids" {
  value = concat(values(aws_cognito_user_pool_client.public)[*].id, values(aws_cognito_user_pool_client.machine)[*].id)
}
