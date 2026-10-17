variable "name" { type = string }
variable "discovery_url" { type = string }
variable "client_id" { type = string }

variable "client_secret" {
  type      = string
  sensitive = true
}

variable "client_credentials_version" {
  description = "Bump to push a rotated client secret into the token vault."
  type        = number
  default     = 1
}
