provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.tags
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

data "aws_caller_identity" "current" {}

locals {
  account        = data.aws_caller_identity.current.account_id
  name           = "bookshelf-vault-alexa-${local.account}"
  short_name     = "bookshelf-vault-alexa"
  # The Alexa+ add-on endpoint (addon.json, `alexa-ai new mcp --mcp-server-url`),
  # the PRM `resource` and the Cognito resource server id. Alexa+ calls this
  # URL directly; the AgentCore Gateway below is an optional experiment.
  oauth_resource = "https://${var.domain}/mcp"
  # Read only: the production pool is identified by its name, never managed here.
  production_user_pool_name = "bookshelf-vault-${local.account}-users"
  tags = {
    Project     = "bookshelf-vault-alexa"
    Environment = "hackathon"
    ManagedBy   = "terraform"
  }
}

# ---- secrets (own, never shared with production) ---------------------------

resource "random_password" "signing" {
  length  = 64
  special = false
}

resource "random_password" "pairing" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "vault" {
  name                    = "${local.name}-signing"
  recovery_window_in_days = 7
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

# ---- data: own table, bucket, queues (the production module, unchanged) -----

module "data" {
  source = "../../modules/data"
  name   = local.name
  tags   = local.tags
}

# ---- DNS + certificate for alexa.bookshelf.example only -----------------------------

module "dns" {
  source             = "../../modules/alexa-dns"
  domain             = var.domain
  cloudflare_zone_id = var.cloudflare_zone_id
  tags               = local.tags
}

# ---- identity: three additions to the shared Cognito pool --------------------

module "identity" {
  source              = "../../modules/alexa-identity"
  name                = local.name
  region              = var.aws_region
  user_pool_name      = local.production_user_pool_name
  resource_identifier = local.oauth_resource
  alexa_redirect_urls = var.alexa_redirect_urls
  identity_providers  = var.identity_providers
}

# ---- compute: Lambdas + REST API with X-Ray ----------------------------------

module "compute" {
  source                    = "../../modules/compute-rest"
  name                      = local.name
  domain                    = var.domain
  certificate_arn           = module.dns.certificate_arn
  mcp_artifact_path         = abspath("${path.module}/../../../.artifacts/mcp-server.zip")
  worker_artifact_path      = abspath("${path.module}/../../../.artifacts/export-worker.zip")
  interceptor_artifact_path = abspath("${path.module}/../../../.artifacts/gateway-interceptor.zip")
  table_name                = module.data.table_name
  table_arn                 = module.data.table_arn
  export_bucket_name        = module.data.export_bucket_name
  export_bucket_arn         = module.data.export_bucket_arn
  export_queue_url          = module.data.export_queue_url
  export_queue_arn          = module.data.export_queue_arn
  cognito_issuer            = module.identity.issuer
  authorized_client_ids     = [module.identity.alexa_client_id, module.identity.service_client_id]
  oauth_resource            = local.oauth_resource
  secrets_arn               = aws_secretsmanager_secret.vault.arn
  tags                      = local.tags
  extra_environment = {
    ALEXA_PROFILE          = "1"
    PUBLIC_BASE_URL        = "https://${var.domain}"
    AUTH_CHALLENGE         = "omit"
    AUTH_ALL_METHODS       = "true"
    AUTH_FACADE            = var.auth_facade
    GATEWAY_CLIENT_IDS     = module.identity.service_client_id
    AUTHORIZATION_ENDPOINT = "https://${var.auth_domain}/oauth2/authorize"
    TOKEN_ENDPOINT         = "https://${var.auth_domain}/oauth2/token"
    ALEXA_DEFAULT_LOCALE   = var.alexa_default_locale
  }
}

resource "cloudflare_record" "alexa" {
  zone_id = var.cloudflare_zone_id
  name    = var.domain
  type    = "CNAME"
  value   = trimsuffix(module.compute.domain_target, ".")
  ttl     = 60
  proxied = false
  # No allow_overwrite: if the name already exists, the apply stops instead of
  # silently taking over a record this state does not own.
}

# ---- AgentCore Identity + Gateway (optional experiment) ------------------------
# Not on the Alexa+ path: the add-on points at local.oauth_resource directly.
# The gateway fronts the same endpoint for the identity/latency experiments
# described in the project runbook.

module "agentcore_identity" {
  source        = "../../modules/agentcore-identity"
  name          = local.short_name
  discovery_url = module.identity.discovery_url
  client_id     = module.identity.service_client_id
  client_secret = module.identity.service_client_secret
}

module "agentcore_gateway" {
  source                 = "../../modules/agentcore-gateway"
  name                   = local.short_name
  discovery_url          = module.identity.discovery_url
  allowed_clients        = [module.identity.alexa_client_id, module.identity.service_client_id]
  supported_versions     = ["2025-11-25", "2026-07-28"]
  upstream_endpoint      = local.oauth_resource
  oauth_provider_arn     = module.agentcore_identity.oauth_provider_arn
  oauth_scopes           = [module.identity.service_scope]
  credential_secret_arn  = module.agentcore_identity.credential_secret_arn
  interceptor_lambda_arn = module.compute.interceptor_lambda_arn
  tags                   = local.tags

  # The MCP-server target is indexed at creation: the endpoint, its DNS and
  # certificate must already answer.
  depends_on = [cloudflare_record.alexa, module.compute]
}

module "agentcore_observability" {
  source                = "../../modules/agentcore-observability"
  name                  = local.short_name
  gateway_arn           = module.agentcore_gateway.gateway_arn
  enable_gateway_traces = var.enable_gateway_traces
  tags                  = local.tags
}

# ---- alarms + budget ----------------------------------------------------------

resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"
}

resource "aws_sns_topic_policy" "alarms" {
  arn = aws_sns_topic.alarms.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdministration"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account}:root" }
        Action    = ["SNS:GetTopicAttributes", "SNS:SetTopicAttributes", "SNS:Subscribe", "SNS:ListSubscriptionsByTopic", "SNS:Publish", "SNS:DeleteTopic"]
        Resource  = aws_sns_topic.alarms.arn
      },
      {
        Sid       = "BudgetsAndAlarmsPublish"
        Effect    = "Allow"
        Principal = { Service = ["budgets.amazonaws.com", "cloudwatch.amazonaws.com"] }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.alarms.arn
        Condition = { StringEquals = { "AWS:SourceAccount" = local.account } }
      },
    ]
  })
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "lambda" {
  for_each = {
    mcp-errors    = { function = module.compute.mcp_lambda_name, metric = "Errors" }
    mcp-throttles = { function = module.compute.mcp_lambda_name, metric = "Throttles" }
  }
  alarm_name          = "${local.name}-${each.key}"
  namespace           = "AWS/Lambda"
  metric_name         = each.value.metric
  dimensions          = { FunctionName = each.value.function }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# Alexa+ asks for < 500 ms round trip; alarm on the API's p95.
resource "aws_cloudwatch_metric_alarm" "latency_p95" {
  alarm_name          = "${local.name}-latency-p95"
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  dimensions          = { ApiName = local.name, Stage = module.compute.stage_name }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 500
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-5xx"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5XXError"
  dimensions          = { ApiName = local.name, Stage = module.compute.stage_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# Scoped to this environment's resources by tag. The production budget module
# is account-wide (no filter), so it is not reused here: an unfiltered $10
# budget would fire on production spend. The tag must be activated once as a
# cost allocation tag (Billing console → Cost allocation tags → "Project"),
# a billing setting, not a resource; until then this budget reports $0.
resource "aws_budgets_budget" "hackathon" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$bookshelf-vault-alexa"]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.alarms.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.alarms.arn]
  }
}
