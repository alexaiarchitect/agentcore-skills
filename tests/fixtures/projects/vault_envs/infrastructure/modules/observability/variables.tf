variable "name" { type = string }
variable "api_id" { type = string }
variable "mcp_lambda_name" { type = string }
variable "worker_lambda_name" { type = string }
variable "export_queue_name" { type = string }
variable "export_dlq_name" { type = string }
variable "table_name" { type = string }
variable "alarm_email" {
  type    = string
  default = ""
}
variable "tags" { type = map(string) }
