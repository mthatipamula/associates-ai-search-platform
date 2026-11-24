variable "name" {
  description = "Short project name used in resource names."
  type        = string
  default     = "kp-search"
}

variable "environment" {
  description = "Environment name, e.g. demo, staging, prod."
  type        = string
  default     = "demo"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "allowed_ingress_cidrs" {
  description = <<-EOT
    CIDR blocks allowed to reach the load balancer, e.g. ["203.0.113.7/32"] for your own IP.
    The demo has no real login (personas are picked in the UI), so keep this narrow.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.allowed_ingress_cidrs) > 0
    error_message = "Set allowed_ingress_cidrs explicitly, e.g. your public IP with /32."
  }
}

variable "certificate_arn" {
  description = "Optional ACM certificate ARN. When set, the ALB serves HTTPS on 443 and redirects HTTP to HTTPS."
  type        = string
  default     = ""
}

# --- API (ECS Fargate) -------------------------------------------------------

variable "api_image_tag" {
  description = "Image tag deployed by Terraform on first apply. CI deploys new tags afterwards."
  type        = string
  default     = "latest"
}

variable "api_cpu" {
  description = "Fargate CPU units for one API task (1024 = 1 vCPU)."
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "Fargate memory (MiB) for one API task. Embedding + re-rank models need ~1 GB."
  type        = number
  default     = 2048
}

variable "api_desired_count" {
  description = "Number of API tasks."
  type        = number
  default     = 1
}

variable "llm_provider" {
  description = "none (offline answers) or bedrock (Claude on Amazon Bedrock; enable model access first)."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["none", "bedrock"], var.llm_provider)
    error_message = "llm_provider must be none or bedrock."
  }
}

variable "llm_model" {
  description = "Claude model id (the app adds the anthropic. prefix on Bedrock)."
  type        = string
  default     = "claude-opus-5-5"
}

# --- Elasticsearch (self-managed on ECS / EC2) --------------------------------

variable "es_image" {
  description = "Elasticsearch container image."
  type        = string
  default     = "docker.elastic.co/elasticsearch/elasticsearch:8.15.3"
}

variable "es_instance_type" {
  description = "EC2 instance type for the Elasticsearch host (x86_64)."
  type        = string
  default     = "t3.large"
}

variable "es_heap" {
  description = "Elasticsearch JVM heap, e.g. 2g. Keep it at most half the container memory."
  type        = string
  default     = "2g"
}

variable "es_container_memory" {
  description = "Hard memory limit (MiB) for the Elasticsearch container."
  type        = number
  default     = 6144
}

variable "es_data_volume_gb" {
  description = "Size (GB) of the encrypted gp3 EBS volume that holds the Elasticsearch data."
  type        = number
  default     = 30
}

# --- CI/CD -------------------------------------------------------------------

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name."
  type        = string
  default     = "mthatipamula/associates-ai-search-platform"
}

variable "github_deploy_branch" {
  description = "Only workflows running on this branch can assume the deploy role."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention."
  type        = number
  default     = 30
}
