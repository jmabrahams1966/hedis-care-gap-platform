variable "project_name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "retention_days" {
  description = "Object Lock default retention (WORM). 6 years is a common HIPAA baseline."
  type        = number
  default     = 2190
}

# Write-once, read-many archive for the audit trail, so an application-level (or
# database-level) compromise can't erase it — see docs/SECURITY_HIPAA.md §4.
# Object Lock must be enabled at bucket creation.
resource "aws_s3_bucket" "audit" {
  bucket              = "${var.project_name}-audit-archive"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

# GOVERNANCE mode: objects can't be deleted/overwritten for the retention window
# except by a principal explicitly granted the bypass permission — which the ECS
# task role deliberately is NOT. So a compromised app can append but never erase.
# (Switch to COMPLIANCE for a hard, no-bypass lock once retention policy is final.)
resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = var.retention_days
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_name" {
  value = aws_s3_bucket.audit.id
}

output "bucket_arn" {
  value = aws_s3_bucket.audit.arn
}
