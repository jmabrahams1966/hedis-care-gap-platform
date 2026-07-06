output "api_url" {
  value = "https://${var.api_subdomain}.${var.domain_name}"
}

output "app_url" {
  value = "https://${var.app_subdomain}.${var.domain_name}"
}

output "alb_dns_name" {
  value = module.ecs.alb_dns_name
}

output "frontend_bucket_name" {
  value = module.frontend.bucket_name
}

output "frontend_distribution_id" {
  value = module.frontend.distribution_id
}

output "database_endpoint" {
  value     = module.database.cluster_endpoint
  sensitive = true
}

output "sms_inbound_topic_arn" {
  description = "Set as the origination phone number's two-way channel ARN once it's provisioned (see docs/DEPLOYMENT.md)"
  value       = module.messaging.sms_inbound_topic_arn
}
