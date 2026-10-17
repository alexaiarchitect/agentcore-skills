variable "name" { type = string }
variable "monthly_limit_usd" {
  type    = number
  default = 20
}
variable "alarm_topic_arn" { type = string }
