terraform {
  required_version = "= 1.14.2"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # AgentCore gateway interceptors, MCP-server targets with listing_mode
      # and write-only OAuth2 provider arguments; `supported_versions` must be
      # confirmed with `terraform providers schema -json`.
      version = ">= 6.64.0, < 7.0.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.52"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}
