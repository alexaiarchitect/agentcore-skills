variable "aws_region" {
  type    = string
  default = "eu-central-1"
}
variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}
variable "cloudflare_zone_id" { type = string }
variable "google_client_id" {
  type      = string
  sensitive = true
  default   = ""
}
variable "google_client_secret" {
  type      = string
  sensitive = true
  default   = ""
}
variable "chatgpt_callback_urls" { type = list(string) }
variable "desktop_callback_urls" {
  type    = list(string)
  default = ["http://127.0.0.1:1455/auth/callback"]
}
variable "test_callback_urls" {
  type    = list(string)
  default = ["http://localhost:8080/callback"]
}
variable "parent_domain" {
  type    = string
  default = "bookshelf.example"
}
variable "github_organization" { type = string }
variable "github_repository" { type = string }
variable "github_oidc_subject_prefix" {
  type    = string
  default = ""
}
variable "existing_github_oidc_provider_arn" {
  type    = string
  default = ""
}
variable "alarm_email" {
  type    = string
  default = ""
}
variable "monthly_budget_usd" {
  type    = number
  default = 20
}
variable "mcp_domain" {
  type    = string
  default = "mcp.bookshelf.example"
}
variable "auth_domain" {
  type    = string
  default = "auth.bookshelf.example"
}
