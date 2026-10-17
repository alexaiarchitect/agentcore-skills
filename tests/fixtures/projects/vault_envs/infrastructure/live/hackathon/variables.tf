variable "aws_region" {
  type    = string
  default = "eu-central-1"
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "cloudflare_zone_id" { type = string }

variable "domain" {
  description = "Public host of the MCP Lambda. The Alexa+ add-on endpoint is https://<domain>/mcp (direct, not the AgentCore Gateway URL); PRM resource and AS metadata issuer derive from it."
  type        = string
  default     = "alexa.bookshelf.example"
}

variable "alexa_default_locale" {
  description = "Speech locale when an Alexa request carries no usable language signal (ALEXA_DEFAULT_LOCALE)."
  type        = string
  default     = "en-US"
  validation {
    condition     = contains(["en-US", "es-ES"], var.alexa_default_locale)
    error_message = "alexa_default_locale must be en-US or es-ES"
  }
}

variable "auth_domain" {
  description = "The production Cognito custom domain (read only: used for endpoint URLs)."
  type        = string
  default     = "auth.bookshelf.example"
}

variable "alexa_redirect_urls" {
  description = "All redirect URLs the Alexa developer console lists for the add-on's account linking."
  type        = list(string)
}

variable "identity_providers" {
  type    = list(string)
  default = ["Google"]
}

variable "auth_facade" {
  description = "off: metadata only (Cognito endpoints). rewrite: serve /oauth2/* and rewrite bare mcp:* scopes."
  type        = string
  default     = "off"
  validation {
    condition     = contains(["off", "rewrite"], var.auth_facade)
    error_message = "auth_facade must be off or rewrite"
  }
}

variable "enable_gateway_traces" {
  description = "Deliver AgentCore Gateway spans to X-Ray; run transaction-search.sh first."
  type        = bool
  default     = false
}

variable "alarm_email" {
  type    = string
  default = ""
}

variable "monthly_budget_usd" {
  type    = number
  default = 10
}
