variable "name" { type = string }
variable "region" { type = string }

variable "user_pool_name" {
  description = "Name of the existing production user pool (read, never managed here)."
  type        = string
}

variable "resource_identifier" {
  description = "New resource server identifier, e.g. https://alexa.bookshelf.example/mcp"
  type        = string
}

variable "alexa_redirect_urls" {
  description = "Every redirect URL the Alexa developer console shows for the add-on (register all of them)."
  type        = list(string)
}

variable "identity_providers" {
  description = "Identity providers already configured on the pool that Alexa users sign in with."
  type        = list(string)
  default     = ["Google"]
}

variable "test_redirect_urls" {
  description = "Loopback redirect for scripts/local/user-token.mjs (PKCE). Empty to disable."
  type        = list(string)
  default     = ["http://localhost:8976/callback"]
}
