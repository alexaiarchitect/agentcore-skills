variable "name" { type = string }
variable "github_organization" { type = string }
variable "github_repository" { type = string }
variable "subject_prefix" {
  type    = string
  default = ""
}
variable "existing_oidc_provider_arn" {
  type    = string
  default = ""
}
variable "tags" { type = map(string) }
