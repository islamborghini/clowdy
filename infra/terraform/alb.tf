# Application Load Balancer -- the production counterpart to infra/lb/nginx.conf.
#
# The health check is the part worth reading. /api/health is a plain liveness
# probe that touches nothing: no database, no Redis, no Docker. That is
# deliberate. A health check that verifies dependencies turns one slow database
# into every task failing its check at once, and the ALB dutifully removes the
# entire fleet from service. Deep checks belong in monitoring, not in the thing
# that decides whether to keep serving traffic.

resource "aws_lb" "main" {
  name               = "${local.name}-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # An invocation can hold a connection for the full 30s function timeout plus
  # dispatch. The 60s default would sever long ones mid-flight.
  idle_timeout = 120

  enable_deletion_protection = false
}

resource "aws_lb_target_group" "control_plane" {
  name        = "${local.name}-cp"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Fargate tasks register by ENI address, not instance

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # Drain time on deregistration. Long enough for an in-flight invocation to
  # finish, short enough that a deploy is not glacial.
  deregistration_delay = 45
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.control_plane.arn
  }
}
