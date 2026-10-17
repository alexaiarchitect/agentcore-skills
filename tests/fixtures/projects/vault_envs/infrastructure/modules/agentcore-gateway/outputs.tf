output "gateway_id" {
  value = aws_bedrockagentcore_gateway.this.gateway_id
}

output "gateway_arn" {
  value = aws_bedrockagentcore_gateway.this.gateway_arn
}

output "gateway_url" {
  description = "The MCP endpoint clients connect to: https://<id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp"
  value       = aws_bedrockagentcore_gateway.this.gateway_url
}

output "gateway_role_arn" {
  value = aws_iam_role.gateway.arn
}

output "target_id" {
  value = aws_bedrockagentcore_gateway_target.vault.target_id
}
