resource "aws_db_subnet_group" "this" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = var.private_subnet_ids
}

# Aurora Serverless v2 Postgres — scales to zero-ish load cheaply for early
# tenants, encrypted at rest with the shared PHI KMS key, never publicly
# accessible (private subnets + security group scoped to ECS tasks only).
resource "aws_rds_cluster" "this" {
  cluster_identifier     = "${var.project_name}-db"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  engine_version         = "16.4"
  database_name          = var.db_name
  master_username        = var.master_username
  master_password        = var.master_password
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]

  storage_encrypted      = true
  kms_key_id             = var.kms_key_arn
  backup_retention_period = 14
  preferred_backup_window = "07:00-09:00"
  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.project_name}-db-final"

  serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.project_name}-db-writer"
  cluster_identifier = aws_rds_cluster.this.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
}
