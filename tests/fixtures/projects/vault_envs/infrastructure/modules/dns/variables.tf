variable "mcp_domain" { type = string }
variable "auth_domain" { type = string }
variable "cloudflare_zone_id" { type = string }
variable "tags" { type = map(string) }

variable "parent_domain" { type = string }
variable "parent_domain_ip" {
  type    = string
  default = "192.0.2.1"
}
