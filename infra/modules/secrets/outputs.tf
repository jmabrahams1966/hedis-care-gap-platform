output "kms_key_arn" {
  value = aws_kms_key.this.arn
}

output "kms_key_id" {
  value = aws_kms_key.this.key_id
}

output "db_credentials_secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}

output "db_master_username" {
  value = "hedis_admin"
}

output "db_master_password" {
  value     = random_password.db_master.result
  sensitive = true
}

output "app_secrets_arn" {
  value = aws_secretsmanager_secret.app_secrets.arn
}

output "jwt_secret" {
  value     = random_password.jwt_secret.result
  sensitive = true
}
