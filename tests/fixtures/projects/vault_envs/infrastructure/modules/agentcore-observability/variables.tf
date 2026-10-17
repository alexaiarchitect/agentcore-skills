variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "gateway_arn" {
  description = "ARN of the gateway resource"
  type        = string
}

variable "name" { type = string }

variable "enable_gateway_traces" {
  description = "Deliver gateway spans to X-Ray. Requires CloudWatch Transaction Search (account-level, transaction-search.sh)."
  type        = bool
  default     = false
}
