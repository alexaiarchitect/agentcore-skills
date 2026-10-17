variable "name" { type = string }
variable "artifact_path" { type = string }
variable "table_arn" { type = string }
variable "secrets_arn" { type = string }
variable "client_ids" { type = list(string) }
variable "issuer" { type = string }
variable "certificate_arn" { type = string }
variable "mcp_domain" {
  type    = string
  default = "mcp.example-vault.test"
}
