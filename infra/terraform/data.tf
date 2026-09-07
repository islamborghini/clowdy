# Stateful services: the control-plane database and the worker registry.
#
# These are the two pieces the local compose stack runs as containers and that
# production has no business running itself. Postgres and Redis are not what
# this project is about, and losing the invocation log to a container restart
# teaches nothing.

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name}-db"
  engine         = "postgres"
  engine_version = "17.2"
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 100 # storage autoscaling, so a full disk is not an outage
  storage_encrypted     = true

  db_name  = "clowdy"
  username = "clowdy"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.data.id]
  publicly_accessible    = false

  backup_retention_period = 7
  skip_final_snapshot     = true # dev convenience; flip this for anything real
  deletion_protection     = false

  # Single-AZ. Multi-AZ doubles the cost for a standby that this project does
  # not need; the tradeoff is a few minutes of downtime during a failover.
  multi_az = false
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "registry" {
  cluster_id           = "${local.name}-registry"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.data.id]

  # Single node with no replica. Everything in here is worker heartbeats and
  # in-flight counters, all of which rebuild themselves within one TTL. Paying
  # for a replica to protect data that regenerates in 15 seconds is waste.
}
