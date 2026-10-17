# Certificate for the hackathon subdomain only.
#
# Deliberately NOT the shared `modules/dns`: that module also manages the apex
# A record and the auth.bookshelf.example certificate. Instantiated a second time it
# would put production DNS under this state (allow_overwrite = true) and a
# destroy of this environment would delete the apex record Cognito's custom
# domain depends on. This module touches one new name and one validation record.
resource "aws_acm_certificate" "this" {
  domain_name       = var.domain
  validation_method = "DNS"
  tags              = var.tags
  lifecycle { create_before_destroy = true }
}

resource "cloudflare_record" "validation" {
  zone_id = var.cloudflare_zone_id
  name    = one(aws_acm_certificate.this.domain_validation_options).resource_record_name
  type    = one(aws_acm_certificate.this.domain_validation_options).resource_record_type
  value   = trimsuffix(one(aws_acm_certificate.this.domain_validation_options).resource_record_value, ".")
  ttl     = 60
  proxied = false
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [cloudflare_record.validation.hostname]
}
