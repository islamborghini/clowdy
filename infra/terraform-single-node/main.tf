# Clowdy on one EC2 instance, running the same docker-compose.yml.
#
# This exists because infra/terraform is the architecture and this is the
# hosting. The full stack -- ALB, NAT gateway, RDS, ElastiCache, Fargate -- is
# roughly $110/month before any traffic, and most of that is fixed cost for
# availability that a portfolio project does not need. This is one instance
# with a public IP running the whole compose topology on itself: still two
# control-plane replicas behind nginx, still three workers, still a real
# scheduler distributing work between them. What it gives up is surviving the
# loss of the machine.
#
#   ~$15/month on a t4g.small, or free for 12 months on a t3.micro under the
#   AWS free tier (set instance_type = "t3.micro").
#
# Apply:
#   tofu init && tofu apply -var="key_name=your-ec2-keypair"
#
# Then point a domain at the output IP and put Caddy or certbot in front for
# TLS. There is deliberately no ALB here -- a load balancer costs more per
# month than the instance it would be balancing.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "clowdy"
      ManagedBy = "terraform"
      Stack     = "single-node"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  description = "t4g.small is arm64 and about $12/mo. t3.micro is free-tier eligible for 12 months."
  type        = string
  default     = "t4g.small"
}

variable "key_name" {
  description = "Existing EC2 key pair name for SSH access."
  type        = string
}

variable "repo_url" {
  type    = string
  default = "https://github.com/islamborghini/clowdy.git"
}

variable "allowed_ssh_cidr" {
  description = "Who may SSH in. Defaults to nobody -- set it to your own IP/32."
  type        = string
  default     = "127.0.0.1/32"
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name = "name"
    # Match the architecture to the instance type: t4g is Graviton (arm64),
    # everything else here is x86_64.
    values = [
      startswith(var.instance_type, "t4g")
      ? "al2023-ami-*-kernel-*-arm64"
      : "al2023-ami-*-kernel-*-x86_64"
    ]
  }
}

# Default VPC on purpose. A single-instance deployment does not need its own
# network, and building one would add a NAT gateway -- twice the cost of the
# instance -- for no benefit.
data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "app" {
  name        = "clowdy-single-node"
  description = "Clowdy all-in-one host"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Frontend"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS, once a certificate is in place"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.app.id]

  root_block_device {
    # Function images, project dependency images, and Postgres data all live
    # on this one disk.
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required"
  }

  user_data = <<-USERDATA
    #!/bin/bash
    set -euxo pipefail

    dnf install -y docker git
    systemctl enable --now docker
    usermod -aG docker ec2-user

    install -d -o ec2-user -g ec2-user /usr/local/lib/docker/cli-plugins
    curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
      "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)"
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

    git clone ${var.repo_url} /opt/clowdy
    chown -R ec2-user:ec2-user /opt/clowdy

    # The frontend container publishes on 3000; map the host's port 80 to it.
    cat > /opt/clowdy/docker-compose.override.yml <<'OVERRIDE'
    services:
      frontend:
        ports:
          - "80:80"
    OVERRIDE

    # API keys are not in the repo. Drop them in /opt/clowdy/.env after the
    # first boot and re-run `docker compose up -d`; the stack starts without
    # them, minus the AI assistant and managed databases.
    touch /opt/clowdy/.env
    chown ec2-user:ec2-user /opt/clowdy/.env /opt/clowdy/docker-compose.override.yml

    cd /opt/clowdy && docker compose up -d --build

    # Restart the stack on reboot.
    cat > /etc/systemd/system/clowdy.service <<'UNIT'
    [Unit]
    Description=Clowdy
    Requires=docker.service
    After=docker.service

    [Service]
    Type=oneshot
    RemainAfterExit=yes
    WorkingDirectory=/opt/clowdy
    ExecStart=/usr/bin/docker compose up -d
    ExecStop=/usr/bin/docker compose down

    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl enable clowdy.service
  USERDATA

  tags = { Name = "clowdy" }
}

# A static address, so the DNS record survives a stop/start of the instance.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
}

output "url" {
  value = "http://${aws_eip.app.public_ip}"
}

output "ssh" {
  value = "ssh ec2-user@${aws_eip.app.public_ip}"
}

output "monthly_cost_estimate" {
  value = "~$15/mo on t4g.small (instance ~$12, 30GB gp3 ~$2.40, EIP free while attached). $0 on t3.micro under the 12-month free tier."
}
