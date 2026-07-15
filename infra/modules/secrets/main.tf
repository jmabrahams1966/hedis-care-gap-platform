# Single KMS CMK used to encrypt the Aurora cluster, Secrets Manager entries, and
# CloudWatch log groups — see docs/SECURITY_HIPAA.md for the encryption-at-rest
# rationale.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

resource "aws_kms_key" "this" {
  description             = "${var.project_name} PHI encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms.json
}

# The default (implicit) key policy only grants the root account access, which
# is enough for RDS/Secrets Manager/ECS since those reach the key through
# IAM identity-based policies. CloudWatch Logs is different: creating a
# KMS-encrypted log group requires the *key policy itself* to grant the
# regional Logs service principal, or CreateLogGroup fails with AccessDenied.
data "aws_iam_policy_document" "kms" {
  # Preserve the default: root account retains full control, so every existing
  # IAM-based grant to this key keeps working.
  statement {
    sid       = "EnableRootAccount"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  # Allow CloudWatch Logs to encrypt/decrypt this project's log group(s).
  statement {
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.name}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${var.project_name}*"]
    }
  }
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

# 64 random bytes, base64-encoded — the AES-256-SIV key for field-level PII
# encryption (app/crypto.py). Kept in Secrets Manager, injected as
# PII_ENCRYPTION_KEY. Losing/rotating this makes existing ciphertext
# unreadable, so it is not regenerated on subsequent applies.
resource "random_id" "pii_key" {
  byte_length = 64
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
    pii_key    = random_id.pii_key.b64_std
  })
}
