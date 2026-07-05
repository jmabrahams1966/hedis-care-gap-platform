output "cluster_endpoint" {
  value = aws_rds_cluster.this.endpoint
}

output "database_name" {
  value = aws_rds_cluster.this.database_name
}

output "port" {
  value = aws_rds_cluster.this.port
}
