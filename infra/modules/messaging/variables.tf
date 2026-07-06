variable "project_name" {
  type = string
}

variable "api_fqdn" {
  description = "Public FQDN of the backend API (e.g. api.example.com) — the SNS HTTPS subscription target"
  type        = string
}
