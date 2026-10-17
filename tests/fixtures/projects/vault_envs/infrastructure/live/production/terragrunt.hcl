remote_state {
  backend = "s3"
  config = {
    bucket       = get_env("TF_STATE_BUCKET")
    key          = "production/bookshelf-vault.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

# No `source` on purpose: copying this directory into the Terragrunt cache would
# break the relative `../../modules` paths, and running in place keeps them valid.
terraform {
  before_hook "require_artifacts" {
    commands = ["plan", "apply"]
    execute  = ["bash", "-c", "test -f ../../../.artifacts/mcp-server.zip && test -f ../../../.artifacts/export-worker.zip"]
  }
}

inputs = {
  aws_region                        = "eu-central-1"
  cloudflare_zone_id                = get_env("TF_VAR_cloudflare_zone_id")
  chatgpt_callback_urls             = jsondecode(get_env("TF_VAR_chatgpt_callback_urls"))
  github_organization               = get_env("TF_VAR_github_organization")
  github_repository                 = get_env("TF_VAR_github_repository")
  github_oidc_subject_prefix        = get_env("TF_VAR_github_oidc_subject_prefix", "")
  existing_github_oidc_provider_arn = get_env("TF_VAR_existing_github_oidc_provider_arn", "")
  alarm_email                       = get_env("TF_VAR_alarm_email", "")
  monthly_budget_usd                = 20
}
