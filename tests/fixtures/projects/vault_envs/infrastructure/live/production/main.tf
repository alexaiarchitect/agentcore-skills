provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.tags
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = local.tags
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

data "aws_caller_identity" "current" {}

# Generated here so no signing material is ever typed by a human, committed, or
# carried in a local .env file.
resource "random_password" "signing" {
  length  = 64
  special = false
}

resource "random_password" "pairing" {
  length  = 64
  special = false
}

# Held in Secrets Manager rather than the function environment, where they would
# be readable from the console and from GetFunctionConfiguration. `ignore_changes`
# on the value lets a key be rotated out of band without Terraform reverting it.
resource "aws_secretsmanager_secret" "vault" {
  name                    = "${local.name}-signing"
  recovery_window_in_days = 7
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "vault" {
  secret_id = aws_secretsmanager_secret.vault.id
  secret_string = jsonencode({
    signingSecret     = random_password.signing.result
    pairingSecret     = random_password.pairing.result
    signingKeyVersion = 1
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

locals {
  name           = "bookshelf-vault-${data.aws_caller_identity.current.account_id}"
  oauth_resource = "https://${var.mcp_domain}/mcp"
  tags = {
    Project     = "bookshelf-vault"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

module "data" {
  source = "../../modules/data"
  name   = local.name
  tags   = local.tags
}

module "dns" {
  source             = "../../modules/dns"
  mcp_domain         = var.mcp_domain
  auth_domain        = var.auth_domain
  parent_domain      = var.parent_domain
  cloudflare_zone_id = var.cloudflare_zone_id
  tags               = local.tags
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
    cloudflare    = cloudflare
  }
}

module "identity" {
  source                = "../../modules/identity"
  name                  = local.name
  auth_domain           = var.auth_domain
  auth_certificate_arn  = module.dns.auth_certificate_arn
  resource_identifier   = local.oauth_resource
  google_client_id      = var.google_client_id
  google_client_secret  = var.google_client_secret
  chatgpt_callback_urls = var.chatgpt_callback_urls
  desktop_callback_urls = var.desktop_callback_urls
  test_callback_urls    = var.test_callback_urls
  tags                  = local.tags
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  depends_on = [module.dns]
}

module "compute" {
  source                = "../../modules/compute"
  name                  = local.name
  mcp_domain            = var.mcp_domain
  mcp_certificate_arn   = module.dns.mcp_certificate_arn
  mcp_artifact_path     = abspath("${path.module}/../../../.artifacts/mcp-server.zip")
  worker_artifact_path  = abspath("${path.module}/../../../.artifacts/export-worker.zip")
  table_name            = module.data.table_name
  table_arn             = module.data.table_arn
  export_bucket_name    = module.data.export_bucket_name
  export_bucket_arn     = module.data.export_bucket_arn
  export_queue_url      = module.data.export_queue_url
  export_queue_arn      = module.data.export_queue_arn
  cognito_issuer        = module.identity.issuer
  authorized_client_ids = module.identity.authorized_client_ids
  oauth_resource        = local.oauth_resource
  secrets_arn           = aws_secretsmanager_secret.vault.arn
  tags                  = local.tags
}

resource "cloudflare_record" "mcp" {
  zone_id         = var.cloudflare_zone_id
  name            = var.mcp_domain
  type            = "CNAME"
  value           = trimsuffix(module.compute.api_domain_target, ".")
  ttl             = 60
  proxied         = false
  allow_overwrite = true
}

resource "cloudflare_record" "auth" {
  zone_id         = var.cloudflare_zone_id
  name            = var.auth_domain
  type            = "CNAME"
  value           = trimsuffix(module.identity.auth_cloudfront_distribution, ".")
  ttl             = 60
  proxied         = false
  allow_overwrite = true
}

module "observability" {
  source             = "../../modules/observability"
  name               = local.name
  api_id             = module.compute.api_id
  mcp_lambda_name    = module.compute.mcp_lambda_name
  worker_lambda_name = module.compute.worker_lambda_name
  export_queue_name  = module.data.export_queue_name
  export_dlq_name    = module.data.export_dlq_name
  table_name         = module.data.table_name
  alarm_email        = var.alarm_email
  tags               = local.tags
}

module "budget" {
  source            = "../../modules/budget"
  name              = local.name
  monthly_limit_usd = var.monthly_budget_usd
  alarm_topic_arn   = module.observability.alarm_topic_arn
}

module "github_oidc" {
  source                     = "../../modules/github-oidc"
  name                       = local.name
  github_organization        = var.github_organization
  github_repository          = var.github_repository
  subject_prefix             = var.github_oidc_subject_prefix
  existing_oidc_provider_arn = var.existing_github_oidc_provider_arn
  tags                       = local.tags
}
