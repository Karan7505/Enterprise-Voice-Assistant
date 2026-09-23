variable "aws_region" {
  description = "AWS region for the whole stack."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Project prefix used in names and bucket names."
  type        = string
  default     = "evoa"
}

variable "environment" {
  description = "Environment label (staging/production)."
  type        = string
  default     = "production"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "rds_instance_class" {
  description = "RDS instance class. db.t4g.micro is fine for staging; use at least db.t3.small (or burstable t4g.small) for real traffic."
  type        = string
  default     = "db.t4g.small"
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ RDS (production)."
  type        = bool
  default     = true
}

variable "rds_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "redis_node_type" {
  description = "ElastiCache node type. cache.t4g.micro for staging, cache.t4g.small for production."
  type        = string
  default     = "cache.t4g.small"
}

variable "redis_num_nodes" {
  description = "Cache node count. Keep 1 with at-rest + transit encryption for v1; scale via replication later if needed."
  type        = number
  default     = 1
}

variable "ecs_cpu" {
  description = "Task CPU units (1 vCPU = 1024)."
  type        = number
  default     = 1024
}

variable "ecs_memory" {
  description = "Task memory in MiB."
  type        = number
  default     = 2048
}

variable "desired_count" {
  description = "Number of API task replicas behind the ALB (blueprint: >= 2 for multi-instance operation)."
  type        = number
  default     = 2
}

variable "container_port" {
  description = "Port the API listens on inside the container."
  type        = number
  default     = 8000
}

variable "certificate_arn" {
  description = "ACM certificate ARN for TLS at the ALB. Empty = HTTP only (staging); set for production."
  type        = string
  default     = ""
}

variable "ecr_repository" {
  description = "ECR repository name for the API image."
  type        = string
  default     = "enterprise-voice-assistant"
}

variable "cors_origins" {
  description = "Comma-separated allowed browser origins (the frontend domain)."
  type        = string
  default     = "https://assistant.example.com"
}

variable "frontend_url" {
  description = "Public frontend URL (referenced in provider attribution headers)."
  type        = string
  default     = "https://assistant.example.com"
}
