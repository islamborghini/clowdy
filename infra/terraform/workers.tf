# Worker fleet on EC2, in an auto scaling group.
#
# Why not Fargate: a worker's entire job is to create containers and exec into
# them. That needs a Docker daemon. Fargate gives a task no daemon, no socket,
# and no privileged mode, so the data plane has to own its host. The control
# plane is serverless; the thing that runs serverless functions is not. AWS
# makes exactly the same split -- Lambda's front end is a managed service, its
# workers are EC2 hosts running Firecracker.
#
# There is no load balancer in front of these. The control plane's scheduler
# picks a worker by consistent hash on the image so warm containers get reused,
# which an ALB cannot express; it would round-robin the same image across every
# instance and turn one warm pool into N cold starts. The scheduler needs to
# address individual workers, so workers register their own IPs in Redis and
# the control plane calls them directly. Service discovery instead of load
# balancing, because the placement decision is the product.

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${local.name}-worker"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# Pull from ECR and ship logs. Nothing else: a worker runs untrusted user code,
# so its instance profile is the blast radius if a function escapes its
# container. It gets no S3, no database, no secrets.
resource "aws_iam_role_policy_attachment" "worker_ecr" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "worker_ssm" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "worker" {
  name = "${local.name}-worker"
  role = aws_iam_role.worker.name
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ec2/${local.name}/worker"
  retention_in_days = 14
}

locals {
  worker_user_data = <<-USERDATA
    #!/bin/bash
    set -euxo pipefail

    dnf install -y docker
    systemctl enable --now docker

    aws ecr get-login-password --region ${var.region} \
      | docker login --username AWS --password-stdin \
        ${split("/", aws_ecr_repository.backend.repository_url)[0]}

    # The base runtime image every function container starts from. Pulled once
    # at boot so the first invocation on a new instance is not also an image
    # pull -- that is the difference between a 700ms cold start and a 30s one.
    docker pull ${aws_ecr_repository.backend.repository_url}:${var.container_image_tag}

    # The worker mounts the host Docker socket: it is the component whose job
    # is to drive the daemon. Everything it launches is still constrained by
    # the memory, CPU, and network limits set in placement_service.py.
    docker run -d --restart always --name clowdy-worker \
      --network host \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -e REDIS_URL="redis://${aws_elasticache_cluster.registry.cache_nodes[0].address}:6379/0" \
      -e WORKER_CONCURRENCY=8 \
      -e WORKER_TTL_SECONDS=15 \
      --log-driver=awslogs \
      --log-opt awslogs-region=${var.region} \
      --log-opt awslogs-group=${aws_cloudwatch_log_group.worker.name} \
      ${aws_ecr_repository.backend.repository_url}:${var.container_image_tag} \
      uvicorn app.worker.main:app --host 0.0.0.0 --port 9000
  USERDATA
}

resource "aws_launch_template" "worker" {
  name_prefix   = "${local.name}-worker-"
  image_id      = data.aws_ssm_parameter.al2023.value
  instance_type = var.worker_instance_type
  user_data     = base64encode(local.worker_user_data)

  iam_instance_profile {
    name = aws_iam_instance_profile.worker.name
  }


  network_interfaces {
    security_groups             = [aws_security_group.worker.id]
    associate_public_ip_address = false
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      # Function images and layers accumulate. 30GB with gp3 is cheap and
      # keeps a busy worker from filling its disk mid-invocation.
      volume_size           = 30
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  metadata_options {
    # IMDSv2 required. A function that escapes its container and reaches the
    # metadata endpoint would otherwise read the instance's IAM credentials
    # with a single unauthenticated GET.
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${local.name}-worker" }
  }
}

resource "aws_autoscaling_group" "worker" {
  name                = "${local.name}-worker"
  vpc_zone_identifier = aws_subnet.private[*].id
  min_size            = var.worker_min_size
  max_size            = var.worker_max_size
  desired_capacity    = var.worker_min_size

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }

  # EC2 health checks only. There is no target group to check against, and a
  # worker that stops heartbeating already falls out of the ring on its own --
  # the registry TTL is the application-level health check.
  health_check_type         = "EC2"
  health_check_grace_period = 120

  instance_refresh {
    strategy = "Rolling"
    preferences {
      # Never drop below the fleet minimum while replacing instances.
      min_healthy_percentage = 100
    }
  }

  tag {
    key                 = "Name"
    value               = "${local.name}-worker"
    propagate_at_launch = true
  }
}

# Scale the fleet on CPU. The better signal is the fleet's aggregate in-flight
# ratio, which the control plane already computes for /api/cluster -- publishing
# that as a custom CloudWatch metric and target-tracking on it is the natural
# next step, and is noted as such in docs/architecture.md rather than faked here.
resource "aws_autoscaling_policy" "worker_cpu" {
  name                   = "${local.name}-worker-cpu"
  autoscaling_group_name = aws_autoscaling_group.worker.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    target_value = 65

    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
  }
}
