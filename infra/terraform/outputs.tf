output "app_url" {
  description = "Public entry point. Point the frontend's VITE_API_URL here, or serve the frontend from CloudFront in front of it."
  value       = "http://${aws_lb.main.dns_name}"
}

output "cluster_endpoint" {
  description = "Live fleet state, for confirming workers registered after an apply."
  value       = "http://${aws_lb.main.dns_name}/api/cluster"
}

output "backend_ecr_repository" {
  description = "Push the backend image here before the first deploy."
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_repository" {
  value = aws_ecr_repository.frontend.repository_url
}

output "database_endpoint" {
  description = "RDS endpoint. Reachable only from inside the VPC."
  value       = aws_db_instance.main.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache endpoint backing the worker registry."
  value       = aws_elasticache_cluster.registry.cache_nodes[0].address
}

output "migrate_command" {
  description = "Run migrations once after the first apply, before scaling the control plane up."
  value       = "aws ecs run-task --cluster ${aws_ecs_cluster.main.name} --task-definition ${aws_ecs_task_definition.control_plane.family} --launch-type FARGATE --overrides '{\"containerOverrides\":[{\"name\":\"control-plane\",\"command\":[\"alembic\",\"upgrade\",\"head\"]}]}'"
}
