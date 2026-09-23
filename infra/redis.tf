# Managed Redis (ElastiCache) — live auth sessions, atomic rate limits, and
# the bounded conversation-context cache. All state here is either
# short-lived (rate-limit windows, session TTLs) or rebuildable (context
# cache from PostgreSQL), so no snapshotting is required for v1.

resource "random_password" "redis" {
  length  = 24
  special = false
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project}-${var.environment}-redis"
  description          = "EVOA session + rate-limit store"

  engine             = "redis"
  engine_version     = "7.1"
  node_type          = var.redis_node_type
  num_cache_clusters = var.redis_num_nodes
  port               = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]
  apply_immediately  = false

  auth_token = random_password.redis.result

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = var.redis_num_nodes > 1

  snapshot_retention_limit = 0

  tags = { Name = "${var.project}-${var.environment}-redis" }
}
