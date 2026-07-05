variable "project_name" {
  type    = string
  default = "hedis-care-gap"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "domain_name" {
  description = "Apex domain claimed in Route 53, e.g. example.com"
  type        = string
}

variable "app_subdomain" {
  description = "Subdomain the React frontend is served from, e.g. app -> app.example.com"
  type        = string
  default     = "app"
}

variable "api_subdomain" {
  description = "Subdomain the FastAPI backend is served from, e.g. api -> api.example.com"
  type        = string
  default     = "api"
}

variable "create_hosted_zone" {
  description = "Set true only if Route 53 doesn't already have a hosted zone for domain_name"
  type        = bool
  default     = false
}

variable "container_image" {
  description = "Backend container image URI (ECR repo:tag). Push an image before the first apply."
  type        = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "task_cpu" {
  type    = number
  default = 512
}

variable "task_memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "db_min_capacity" {
  description = "Aurora Serverless v2 minimum ACUs"
  type        = number
  default     = 0.5
}

variable "db_max_capacity" {
  description = "Aurora Serverless v2 maximum ACUs"
  type        = number
  default     = 4
}

variable "db_name" {
  type    = string
  default = "hedis_care_gap"
}

variable "db_master_username" {
  type    = string
  default = "hedis_admin"
}

variable "ses_from_email" {
  description = "Verified SES sender address, e.g. no-reply@app.example.com"
  type        = string
}

variable "sms_origination_phone" {
  description = "AWS End User Messaging origination number (provision separately, toll-free/10DLC verification takes days)"
  type        = string
  default     = ""
}
