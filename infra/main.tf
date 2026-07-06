module "network" {
  source       = "./modules/network"
  project_name = var.project_name
}

module "secrets" {
  source       = "./modules/secrets"
  project_name = var.project_name
}

module "database" {
  source              = "./modules/database"
  project_name        = var.project_name
  private_subnet_ids  = module.network.private_subnet_ids
  security_group_id   = module.network.database_security_group_id
  kms_key_arn         = module.secrets.kms_key_arn
  db_name             = var.db_name
  master_username     = module.secrets.db_master_username
  master_password     = module.secrets.db_master_password
  min_capacity        = var.db_min_capacity
  max_capacity        = var.db_max_capacity
}

# Assembled connection string, stored as its own plain-text secret so the ECS
# task can inject it directly as DATABASE_URL without building it at runtime.
resource "aws_secretsmanager_secret" "database_url" {
  name       = "${var.project_name}/database-url"
  kms_key_id = module.secrets.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql+asyncpg://${module.secrets.db_master_username}:${module.secrets.db_master_password}@${module.database.cluster_endpoint}:${module.database.port}/${module.database.database_name}"
}

module "dns" {
  source = "./modules/dns"
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }
  domain_name        = var.domain_name
  app_subdomain      = var.app_subdomain
  api_subdomain      = var.api_subdomain
  create_hosted_zone = var.create_hosted_zone
}

module "ecs" {
  source                       = "./modules/ecs"
  project_name                 = var.project_name
  vpc_id                       = module.network.vpc_id
  public_subnet_ids            = module.network.public_subnet_ids
  private_subnet_ids           = module.network.private_subnet_ids
  alb_security_group_id        = module.network.alb_security_group_id
  ecs_tasks_security_group_id  = module.network.ecs_tasks_security_group_id
  container_image              = var.container_image
  container_port               = var.container_port
  task_cpu                     = var.task_cpu
  task_memory                  = var.task_memory
  desired_count                = var.desired_count
  certificate_arn               = module.dns.api_certificate_arn
  zone_id                       = module.dns.zone_id
  api_fqdn                      = "${var.api_subdomain}.${var.domain_name}"
  kms_key_arn                   = module.secrets.kms_key_arn
  database_url_secret_arn       = aws_secretsmanager_secret.database_url.arn
  app_secrets_arn               = module.secrets.app_secrets_arn
  outreach_cron_schedule        = var.outreach_cron_schedule

  environment_variables = {
    DEV_MODE                = "false"
    CORS_ORIGINS            = "https://${var.app_subdomain}.${var.domain_name}"
    DEFAULT_TENANT_SLUG     = "demo"
    AWS_REGION               = var.aws_region
    SES_FROM_EMAIL           = var.ses_from_email
    SES_CONFIGURATION_SET    = "${var.project_name}"
    SMS_ORIGINATION_NUMBER   = var.sms_origination_phone
    SMS_CONFIGURATION_SET    = module.messaging.configuration_set_name
    KMS_KEY_ARN              = module.secrets.kms_key_arn
  }
}

module "messaging" {
  source       = "./modules/messaging"
  project_name = var.project_name
  api_fqdn     = "${var.api_subdomain}.${var.domain_name}"
}

module "frontend" {
  source          = "./modules/frontend"
  project_name    = var.project_name
  app_fqdn        = "${var.app_subdomain}.${var.domain_name}"
  certificate_arn = module.dns.app_certificate_arn
  zone_id         = module.dns.zone_id
}
