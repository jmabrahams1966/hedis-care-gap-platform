variable "project_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "ecs_tasks_security_group_id" {
  type = string
}

variable "container_image" {
  type = string
}

variable "container_port" {
  type = number
}

variable "task_cpu" {
  type = number
}

variable "task_memory" {
  type = number
}

variable "desired_count" {
  type = number
}

variable "certificate_arn" {
  type = string
}

variable "zone_id" {
  type = string
}

variable "api_fqdn" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "audit_bucket_arn" {
  description = "ARN of the WORM audit-archive S3 bucket the app appends to"
  type        = string
}

variable "database_url_secret_arn" {
  description = "ARN of a plain-string secret holding the full asyncpg DATABASE_URL"
  type        = string
}

variable "app_secrets_arn" {
  description = "ARN of the JSON secret containing jwt_secret"
  type        = string
}

variable "environment_variables" {
  description = "Non-secret env vars for the backend container"
  type        = map(string)
}

variable "outreach_cron_schedule" {
  description = "EventBridge Scheduler expression for the outreach batch job"
  type        = string
  default     = "rate(1 day)"
}
