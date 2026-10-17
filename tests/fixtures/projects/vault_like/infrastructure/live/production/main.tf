provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

module "identity" {
  source        = "../../modules/identity"
  name          = "example-vault"
  callback_urls = ["https://assistant.example.test/callback"]
}

module "compute" {
  source          = "../../modules/compute"
  name            = "example-vault"
  artifact_path   = "../../../.artifacts/mcp-server.zip"
  table_arn       = "arn:aws:dynamodb:eu-central-1:111122223333:table/example"
  secrets_arn     = "arn:aws:secretsmanager:eu-central-1:111122223333:secret:example"
  client_ids      = module.identity.authorized_client_ids
  issuer          = module.identity.issuer
  certificate_arn = "arn:aws:acm:eu-central-1:111122223333:certificate/example"
}
