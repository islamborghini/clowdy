# Provider and state configuration.
#
# The backend block is commented out because a portfolio repo should not carry
# a hardcoded bucket name, and because `terraform init` against a bucket that
# does not exist is a bad first experience. Uncomment it before the second
# person touches this stack -- local state is fine for one operator and a
# disaster for two.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # backend "s3" {
  #   bucket         = "clowdy-tfstate"
  #   key            = "clowdy/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "clowdy-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "clowdy"
      ManagedBy = "terraform"
      Env       = var.environment
    }
  }
}
