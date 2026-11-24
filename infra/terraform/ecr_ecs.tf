# --- Container registry --------------------------------------------------------

resource "aws_ecr_repository" "api" {
  name                 = "${local.prefix}-api"
  image_tag_mutability = "MUTABLE" # "latest" is moved on each deploy; deploys use immutable git-SHA tags
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

# --- ECS cluster ---------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = local.prefix
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", aws_ecs_capacity_provider.es.name]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.prefix}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "es" {
  name              = "/ecs/${local.prefix}/elasticsearch"
  retention_in_days = var.log_retention_days
}

# Private DNS so the API finds Elasticsearch at elasticsearch.<prefix>.internal
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${local.prefix}.internal"
  vpc  = aws_vpc.main.id
}

# --- Secrets -------------------------------------------------------------------

resource "random_password" "elastic" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "elastic" {
  name                    = "${local.prefix}/elastic-password"
  description             = "Password of the elastic superuser"
  recovery_window_in_days = 0 # demo: allow destroy/re-create without a 7-30 day wait
}

resource "aws_secretsmanager_secret_version" "elastic" {
  secret_id     = aws_secretsmanager_secret.elastic.id
  secret_string = random_password.elastic.result
}
