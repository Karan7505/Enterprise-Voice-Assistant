# PostgreSQL (RDS) — the durable source of truth (users, auth_sessions,
# chat history, memories, audio ownership, action audit trail).
#
# The application runs Alembic migrations on startup, so no bootstrap SQL is
# needed here; the schema is owned by the repo (alembic/versions/).

resource "random_password" "rds" {
  length  = 20
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier     = "${var.project}-${var.environment}-postgres"
  engine         = "postgres"
  engine_version = "15"
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage_gb
  max_allocated_storage = var.rds_allocated_storage_gb * 4
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "assistant"
  username = "evoa"
  password = random_password.rds.result

  multi_az               = var.rds_multi_az
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  availability_zone      = data.aws_availability_zones.available.names[0]
  apply_immediately      = false

  backup_retention_period      = 7
  auto_minor_version_upgrade   = true
  performance_insights_enabled = true

  deletion_protection       = var.environment == "production"
  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "${var.project}-${var.environment}-final" : null
}
