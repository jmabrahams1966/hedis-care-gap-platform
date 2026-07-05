# Single KMS CMK used to encrypt the Aurora cluster, Secrets Manager entries, and
# CloudWatch log groups — see docs/SECURITY_HIPAA.md for the encryption-at-rest
# rationale.
resource "aws_kms_key" "this" {
  description             = "${var.project_name} PHI encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.project_name}"
  target_key_id = aws_kms_key.this.key_id
}

resource "random_password" "db_master" {
  length  = 32
  special = false
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name       = "${var.project_name}/db-credentials"
  kms_key_id = aws_kms_key.this.arn
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = "hedis_admin"
    password = random_password.db_master.result
  })
}

resource "aws_secretsmanager_secret" "app_secrets" {
  name       = "${var.project_name}/app-secrets"
  kms_key_id = aws_kms_key.this.arn
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    jwt_secret = random_password.jwt_secret.result
  })
}
