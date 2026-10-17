output "api_id" { value = aws_apigatewayv2_api.mcp.id }
output "api_endpoint" { value = aws_apigatewayv2_api.mcp.api_endpoint }
output "api_domain_target" { value = aws_apigatewayv2_domain_name.mcp.domain_name_configuration[0].target_domain_name }
output "mcp_lambda_name" { value = aws_lambda_function.mcp.function_name }
output "worker_lambda_name" { value = aws_lambda_function.worker.function_name }
output "api_stage_arn" { value = aws_apigatewayv2_stage.production.arn }
