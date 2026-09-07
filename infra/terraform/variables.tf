variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name, used in resource names and tags."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = <<-EOT
    Number of availability zones to spread across.

    Two is the minimum an ALB will accept, and it is also the point of the
    exercise: a single-AZ deployment is not highly available, it is a
    single-machine deployment with extra billing.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2
    error_message = "An ALB requires subnets in at least two availability zones."
  }
}

variable "control_plane_count" {
  description = "Number of control-plane tasks behind the ALB."
  type        = number
  default     = 2
}

variable "control_plane_cpu" {
  description = "Fargate CPU units per control-plane task (1024 = 1 vCPU)."
  type        = number
  default     = 512
}

variable "control_plane_memory" {
  description = "Fargate memory (MiB) per control-plane task."
  type        = number
  default     = 1024
}

variable "worker_instance_type" {
  description = <<-EOT
    EC2 instance type for the worker fleet.

    Workers run on EC2, not Fargate, and that is the central deployment
    decision in this stack. A worker's whole job is to create and exec into
    containers, which needs a Docker daemon and a writable container runtime.
    Fargate gives a task no access to a daemon at all -- there is no socket to
    mount and no privileged mode. So the control plane, which is stateless
    HTTP, runs serverless; the data plane, which needs the host, runs on
    instances it controls. This is the same split AWS itself makes: Lambda's
    front end is managed service, its workers are EC2 hosts running
    Firecracker.
  EOT
  type        = string
  default     = "t3.medium"
}

variable "worker_min_size" {
  description = "Minimum worker instances."
  type        = number
  default     = 2
}

variable "worker_max_size" {
  description = "Maximum worker instances the ASG may scale to."
  type        = number
  default     = 6
}

variable "db_instance_class" {
  description = "RDS instance class for the control-plane database."
  type        = string
  default     = "db.t4g.micro"
}

variable "redis_node_type" {
  description = "ElastiCache node type for the worker registry."
  type        = string
  default     = "cache.t4g.micro"
}

variable "db_password" {
  description = "Master password for RDS. Supply via TF_VAR_db_password, never in a .tfvars file that gets committed."
  type        = string
  sensitive   = true
}

variable "container_image_tag" {
  description = "Image tag to deploy for both control plane and workers."
  type        = string
  default     = "latest"
}
