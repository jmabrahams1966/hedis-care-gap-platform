variable "project_name" {
  type = string
}

variable "app_fqdn" {
  type = string
}

variable "api_fqdn" {
  description = "API host, used in the frontend CSP connect-src"
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN in us-east-1"
  type        = string
}

variable "zone_id" {
  type = string
}
