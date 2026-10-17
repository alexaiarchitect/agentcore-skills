output "mcp_certificate_arn" { value = aws_acm_certificate_validation.mcp.certificate_arn }
output "auth_certificate_arn" { value = aws_acm_certificate_validation.auth.certificate_arn }

output "apex_record_hostname" { value = cloudflare_record.apex.hostname }
