# Values consumed by the deploy pipeline (GitHub repo variables) and the
# runbooks. None of these contain secrets.

output "ecr_repository_uri" {
  description = "Base URI of the ECR repository (pipeline pushes here)."
  value       = aws_ecr_repository.api.repository_url
}

output "ecs_cluster" {
  description = "ECS cluster name (pipeline variable ECS_CLUSTER)."
  value       = aws_ecs_cluster.main.name
}

output "ecs_task_family" {
  description = "Task definition family (pipeline variable ECS_TASK_FAMILY)."
  value       = aws_ecs_task_definition.api.family
}

output "ecs_service" {
  description = "ECS service name (pipeline variable ECS_SERVICE)."
  value       = aws_ecs_service.api.name
}

output "alb_dns_name" {
  description = "Public DNS name of the load balancer."
  value       = aws_lb.main.dns_name
}

output "app_secret_arn" {
  description = "Secrets Manager secret holding the runtime secrets."
  value       = aws_secretsmanager_secret.app.arn
  sensitive   = true
}

output "s3_audio_bucket" {
  description = "Audio store bucket (set as S3_BUCKET)."
  value       = aws_s3_bucket.audio.bucket
}

output "rds_endpoint" {
  description = "RDS endpoint host:port (reference only; the app reads DATABASE_URL from the secret)."
  value       = aws_db_instance.main.endpoint
}

output "rds_username" {
  value = aws_db_instance.main.username
}

output "redis_primary_endpoint" {
  description = "Redis primary endpoint host:port (reference only; the app reads REDIS_URL from the secret)."
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "vpc_id" {
  value = aws_vpc.main.id
}
