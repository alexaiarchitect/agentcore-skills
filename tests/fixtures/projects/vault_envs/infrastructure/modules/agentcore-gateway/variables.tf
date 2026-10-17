variable "name" {
  type    = string
  default = "bookshelf-vault-alexa"
}

variable "target_name" {
  description = "Becomes the tool-name prefix: <target_name>___<tool>. Keep it short; tool names are limited to 256 characters."
  type        = string
  default     = "vault"
}

variable "discovery_url" {
  description = "OIDC discovery URL, e.g. https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration"
  type        = string
}

variable "allowed_clients" {
  description = "App client ids whose tokens may call the gateway (checked against the client_id claim)."
  type        = list(string)
}

variable "allowed_scopes" {
  type    = list(string)
  default = []
}

variable "supported_versions" {
  type    = list(string)
  default = ["2025-11-25", "2026-07-28"]
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "upstream_endpoint" {
  description = "HTTPS URL of the existing MCP endpoint the gateway fronts. The Alexa+ add-on calls this URL directly; the gateway is an optional experiment."
  type        = string
  default     = "https://alexa.bookshelf.example/mcp"
}

variable "oauth_provider_arn" {
  description = "aws_bedrockagentcore_oauth2_credential_provider.<name>.credential_provider_arn"
  type        = string
}

variable "oauth_scopes" {
  type    = list(string)
  default = []
}

variable "interceptor_lambda_arn" {
  description = "REQUEST interceptor that forwards the end user's token (apps/gateway-interceptor)"
  type        = string
}

variable "credential_secret_arn" {
  description = "The provider's client_secret_arn (Secrets Manager) the gateway role reads"
  type        = string
}
