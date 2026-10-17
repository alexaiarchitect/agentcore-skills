variable "name" { type = string }
variable "mcp_domain" { type = string }
variable "mcp_certificate_arn" { type = string }
variable "mcp_artifact_path" { type = string }
variable "worker_artifact_path" { type = string }
variable "table_name" { type = string }
variable "table_arn" { type = string }
variable "export_bucket_name" { type = string }
variable "export_bucket_arn" { type = string }
variable "export_queue_url" { type = string }
variable "export_queue_arn" { type = string }
variable "cognito_issuer" { type = string }
variable "authorized_client_ids" { type = list(string) }
variable "oauth_resource" { type = string }

variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" { type = map(string) }

variable "secrets_arn" {
  type = string
}
variable "sharing_enabled" {
  type    = bool
  default = true
}

# -1 leaves a function unreserved. Reserving carves capacity out of the account
# pool, so the export worker cannot consume everything and starve the API; AWS
# also requires at least 100 unreserved to remain, which 20 + 2 out of 1000
# comfortably satisfies.
variable "mcp_reserved_concurrency" {
  type    = number
  default = 20
}
variable "worker_reserved_concurrency" {
  type    = number
  default = 2
}
