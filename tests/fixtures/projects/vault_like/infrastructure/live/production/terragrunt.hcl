remote_state {
  backend = "s3"
  config = {
    bucket       = get_env("TF_STATE_BUCKET")
    key          = "production/example-vault.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}
