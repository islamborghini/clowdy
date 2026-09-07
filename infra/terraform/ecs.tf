# Control plane on ECS Fargate.
#
# Fargate rather than EC2 for this half of the platform because the control
# plane is ordinary stateless HTTP: no daemon to reach, no host state, nothing
# that survives a task. Handing AWS the capacity planning for it is the whole
# value proposition, and it means scaling the API has nothing to do with
# scaling execution capacity. See workers.tf for why the other half is EC2.

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "control_plane" {
  name              = "/ecs/${local.name}/control-plane"
  retention_in_days = 14 # unbounded log retention is a bill, not a feature
}

# --- IAM -------------------------------------------------------------------
#
# Two roles, because they are used by two different principals at two different
# times. The execution role belongs to the ECS agent and is used before the
# container starts, to pull the image and write logs. The task role belongs to
# the application code itself. Merging them would hand the running container
# ECR pull rights it never needs.

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${local.name}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Secrets are pulled from Secrets Manager at task start rather than baked into
# the task definition, where they would be readable by anyone with
# ecs:DescribeTaskDefinition.
data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.app.arn]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "read-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}-app"
  recovery_window_in_days = 0 # dev: allow immediate recreate under the same name
}

# Populate this out of band (console or `aws secretsmanager put-secret-value`).
# Terraform deliberately does not write the values: anything it writes lands in
# the state file in plaintext.
resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    GROQ_API_KEY   = "replace-me"
    CLERK_JWKS_URL = "replace-me"
    NEON_API_KEY   = "replace-me"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# --- Task definition and service -------------------------------------------

resource "aws_ecs_task_definition" "control_plane" {
  family                   = "${local.name}-control-plane"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.control_plane_cpu
  memory                   = var.control_plane_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "control-plane"
    image     = "${aws_ecr_repository.backend.repository_url}:${var.container_image_tag}"
    essential = true
    command   = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = [
      {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://clowdy:${var.db_password}@${aws_db_instance.main.endpoint}/clowdy"
      },
      {
        name  = "REDIS_URL"
        value = "redis://${aws_elasticache_cluster.registry.cache_nodes[0].address}:6379/0"
      },
      # One task runs migrations, not all of them. See the migrate service in
      # docker-compose.yml for the local equivalent.
      { name = "RUN_MIGRATIONS", value = "false" },
    ]

    secrets = [
      for key in ["GROQ_API_KEY", "CLERK_JWKS_URL", "NEON_API_KEY"] : {
        name      = key
        valueFrom = "${aws_secretsmanager_secret.app.arn}:${key}::"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.control_plane.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "cp"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')\" || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
  }])
}

resource "aws_ecs_service" "control_plane" {
  name            = "${local.name}-control-plane"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.control_plane.arn
  desired_count   = var.control_plane_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.control_plane.id]
    assign_public_ip = false # private subnets reach the internet via NAT
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.control_plane.arn
    container_name   = "control-plane"
    container_port   = 8000
  }

  # Rolling deploy that never drops below the current capacity: bring new tasks
  # up to 200 percent, then drain the old ones.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Give a new task time to pass its health check before the ALB judges it.
  health_check_grace_period_seconds = 60

  depends_on = [aws_lb_listener.http]
}

# Scale on CPU. Deliberately not on request count: the control plane hands work
# off to the fleet and spends most invocations waiting on a worker, so its CPU
# tracks real load while its request count tracks how slow the workers are.
resource "aws_appautoscaling_target" "control_plane" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.control_plane.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.control_plane_count
  max_capacity       = var.control_plane_count * 4
}

resource "aws_appautoscaling_policy" "control_plane_cpu" {
  name               = "${local.name}-cp-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.control_plane.service_namespace
  resource_id        = aws_appautoscaling_target.control_plane.resource_id
  scalable_dimension = aws_appautoscaling_target.control_plane.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    scale_in_cooldown  = 300 # slow to shrink: flapping costs more than a spare task
    scale_out_cooldown = 60  # fast to grow
  }
}
