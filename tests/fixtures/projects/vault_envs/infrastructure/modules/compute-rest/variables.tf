variable "name" { type = string }
variable "domain" { type = string }
variable "certificate_arn" { type = string }
variable "mcp_artifact_path" { type = string }
variable "worker_artifact_path" { type = string }
variable "interceptor_artifact_path" { type = string }
variable "table_name" { type = string }
variable "table_arn" { type = string }
variable "export_bucket_name" { type = string }
variable "export_bucket_arn" { type = string }
variable "export_queue_url" { type = string }
variable "export_queue_arn" { type = string }
variable "cognito_issuer" { type = string }
variable "authorized_client_ids" { type = list(string) }
variable "oauth_resource" { type = string }
variable "secrets_arn" { type = string }
variable "tags" { type = map(string) }

variable "extra_environment" {
  description = "Profile settings for the MCP function (ALEXA_PROFILE, PUBLIC_BASE_URL, ...)."
  type        = map(string)
  default     = {}
}

variable "stage_name" {
  type    = string
  default = "hackathon"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# 1024 MB gives the function a full vCPU share on arm64; the latency budget is 500 ms.
variable "mcp_memory_mb" {
  type    = number
  default = 1024
}

variable "mcp_reserved_concurrency" {
  type    = number
  default = 10
}

variable "worker_reserved_concurrency" {
  type    = number
  default = 1
}

variable "throttle_rate" {
  type    = number
  default = 20
}

variable "throttle_burst" {
  type    = number
  default = 40
}

variable "enable_access_logs" {
  type    = bool
  default = false
}
