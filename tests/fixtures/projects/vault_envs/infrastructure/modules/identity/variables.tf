variable "name" { type = string }
variable "auth_domain" { type = string }
variable "auth_certificate_arn" { type = string }
variable "resource_identifier" { type = string }
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
variable "tags" { type = map(string) }
