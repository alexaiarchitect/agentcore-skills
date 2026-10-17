output "rest_api_id" { value = aws_api_gateway_rest_api.mcp.id }
output "stage_name" { value = aws_api_gateway_stage.mcp.stage_name }
output "domain_target" { value = aws_api_gateway_domain_name.mcp.regional_domain_name }
output "mcp_lambda_name" { value = aws_lambda_function.mcp.function_name }
output "worker_lambda_name" { value = aws_lambda_function.worker.function_name }
output "interceptor_lambda_arn" { value = aws_lambda_function.interceptor.arn }
output "interceptor_lambda_name" { value = aws_lambda_function.interceptor.function_name }
