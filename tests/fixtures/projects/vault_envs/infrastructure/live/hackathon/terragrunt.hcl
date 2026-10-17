# Alexa+ hackathon environment. Same AWS
# account and state bucket as production, separate state key, separate
# resources (prefix bookshelf-vault-alexa-<account>), subdomain alexa.bookshelf.example.
# The project runbook lists every resource it creates and the three objects
# it adds to the shared Cognito user pool.
remote_state {
  backend = "s3"
  config = {
    bucket       = get_env("TF_STATE_BUCKET")
    key          = "hackathon/bookshelf-vault-alexa.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

# No `source`, as in production: running in place keeps ../../modules valid.
terraform {
  before_hook "require_artifacts" {
    commands = ["plan", "apply"]
    execute  = ["bash", "-c", "test -f ../../../.artifacts/mcp-server.zip && test -f ../../../.artifacts/export-worker.zip && test -f ../../../.artifacts/gateway-interceptor.zip"]
  }
}

inputs = {
  aws_region           = "eu-central-1"
  cloudflare_zone_id   = get_env("TF_VAR_cloudflare_zone_id")
  alexa_redirect_urls  = jsondecode(get_env("TF_VAR_alexa_redirect_urls", "[\"https://alexa.amazon.com/api/skill/link/REPLACE_WITH_VENDOR_ID\"]"))
  alarm_email          = get_env("TF_VAR_alarm_email", "")
  auth_facade          = get_env("TF_VAR_auth_facade", "off")
  alexa_default_locale = get_env("TF_VAR_alexa_default_locale", "en-US")
  monthly_budget_usd   = 10
}
