terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state in S3 with native lock files (Terraform >= 1.10).
  # Configure with: terraform init -backend-config=backend.hcl
  # (copy backend.hcl.example to backend.hcl first).
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  prefix     = "${var.name}-${var.environment}"
  azs        = slice(data.aws_availability_zones.available.names, 0, 2)
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
}
