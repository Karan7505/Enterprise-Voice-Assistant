# Compute: ECS Fargate behind an Application LB.
#
# The task definition is the ONLY Terraform-managed artifact the CI/CD
# pipeline rewrites per deploy: it registers a new revision with the same
# family and a swapped image (aws ecs register-task-definition --source
# semantics), so no other resource in this file is touched by deploys.

resource "aws_ecr_repository" "api" {
  name                 = var.ecr_repository
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images for rollback"
      selectionCriteria = {
        tagStatus = "any"
      }
      action = {
        type        = "count"
        countUnit   = "images"
        countNumber = 10
      }
    }]
  })
}

# --- task roles -------------------------------------------------------------

data "aws_iam_policy_document" "task" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      aws_s3_bucket.audio.arn,
      "${aws_s3_bucket.audio.arn}/*",
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.app.arn]
  }
}

resource "aws_iam_role" "task" {
  name               = "${var.project}-${var.environment}-api-task-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

data "aws_iam_policy_document" "task_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_iam_role" "execution" {
  name               = "${var.project}-${var.environment}-api-exec-role"
  assume_role_policy = data.aws_iam_policy_document.execution_assume.json
}

data "aws_iam_policy_document" "execution_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy" "ecr" {
  arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "execution_ecr" {
  role       = aws_iam_role.execution.name
  policy_arn = data.aws_iam_policy.ecr.arn
}

# --- cluster, LB, service ----------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-${var.environment}-api"
  retention_in_days = 30
}

resource "aws_lb" "main" {
  name               = "${var.project}-${var.environment}-alb"
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project}-${var.environment}-api"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    # The API has no /health route; /auth/me without a token returns 401,
    # which proves the app + auth stack are alive. 401 counts as healthy.
    enabled             = true
    path                = "/auth/me"
    matcher             = "200,401"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
  }
}

# The API has no /health route yet; until one ships, probe an always-present
# endpoint that answers without auth (401 still counts as "healthy" via the
# success_codes below).
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener" "https" {
  count = var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener_rule" "http_redirect" {
  count = var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  condition {
    path_pattern {
      values = ["*"]
    }
  }

  action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# --- task definition (base revision; pipeline registers new revisions) -------

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-${var.environment}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name = "api"
    # Placeholder image: the deploy pipeline registers each revision with the
    # real ECR image (same family), so this value is never served.
    image        = "${aws_ecr_repository.api.repository_url}:000000000000"
    essential    = true
    portMappings = [{ containerPort = var.container_port, protocol = "tcp" }]

    environment = [
      { name = "S3_BUCKET", value = aws_s3_bucket.audio.bucket },
      { name = "S3_REGION", value = var.aws_region },
      { name = "LOG_FORMAT", value = "json" },
      { name = "COOKIE_SECURE", value = "true" },
      { name = "CORS_ORIGINS", value = var.cors_origins },
      { name = "FRONTEND_URL", value = var.frontend_url },
    ]

    # Runtime-injected secrets: ARN + key only, values never stored here.
    secrets = [
      for k in [
        "DATABASE_URL", "REDIS_URL",
        "S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY",
        "OPENROUTER_API_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY",
        "ELEVENLABS_API_KEY", "TTS_API_KEY",
        "CRM_REST_API_KEY", "WA_TOKEN", "EMAIL_USERNAME", "EMAIL_PASSWORD",
        ] : {
        name      = k
        valueFrom = "${aws_secretsmanager_secret.app.arn}:${k}::"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${var.project}-${var.environment}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    # Public subnets: tasks need a public IP for egress to LLM/TTS/SMTP
    # providers (inbound from the ALB uses the VPC IPs).
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
    # task_definition: the pipeline registers/points at fresh revisions.
    # desired_count: scale via `aws ecs update-service` or TF, per runbook.
  }
}
