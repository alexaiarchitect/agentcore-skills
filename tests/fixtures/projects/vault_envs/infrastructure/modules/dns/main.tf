# AWS refuses to create a Cognito user-pool custom domain unless the parent
# domain already resolves. The placeholder is in the RFC 5737 documentation
# range, so it routes nowhere and exposes no service.
resource "cloudflare_record" "apex" {
  zone_id         = var.cloudflare_zone_id
  name            = var.parent_domain
  type            = "A"
  value           = var.parent_domain_ip
  ttl             = 300
  proxied         = false
  allow_overwrite = true
}

resource "aws_acm_certificate" "mcp" {
  domain_name       = var.mcp_domain
  validation_method = "DNS"
  tags              = var.tags
  lifecycle { create_before_destroy = true }
}

resource "aws_acm_certificate" "auth" {
  provider          = aws.us_east_1
  domain_name       = var.auth_domain
  validation_method = "DNS"
  tags              = var.tags
  lifecycle { create_before_destroy = true }
}

resource "cloudflare_record" "mcp_certificate" {
  zone_id         = var.cloudflare_zone_id
  name            = one(aws_acm_certificate.mcp.domain_validation_options).resource_record_name
  type            = one(aws_acm_certificate.mcp.domain_validation_options).resource_record_type
  value           = trimsuffix(one(aws_acm_certificate.mcp.domain_validation_options).resource_record_value, ".")
  ttl             = 60
  proxied         = false
  allow_overwrite = true
}

resource "cloudflare_record" "auth_certificate" {
  zone_id         = var.cloudflare_zone_id
  name            = one(aws_acm_certificate.auth.domain_validation_options).resource_record_name
  type            = one(aws_acm_certificate.auth.domain_validation_options).resource_record_type
  value           = trimsuffix(one(aws_acm_certificate.auth.domain_validation_options).resource_record_value, ".")
  ttl             = 60
  proxied         = false
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "mcp" {
  certificate_arn         = aws_acm_certificate.mcp.arn
  validation_record_fqdns = [cloudflare_record.mcp_certificate.hostname]
}

resource "aws_acm_certificate_validation" "auth" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.auth.arn
  validation_record_fqdns = [cloudflare_record.auth_certificate.hostname]
}
