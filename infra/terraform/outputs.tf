output "app_url" {
  description = "Open this in a browser (from an allowed IP)."
  value       = var.certificate_arn == "" ? "http://${aws_lb.api.dns_name}" : "https://${aws_lb.api.dns_name}"
}

output "aws_region" {
  value = var.aws_region
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "api_service" {
  value = aws_ecs_service.api.name
}

output "api_task_family" {
  value = aws_ecs_task_definition.api.family
}

output "private_subnet_ids" {
  description = "For one-off tasks such as seeding the index."
  value       = join(",", aws_subnet.private[*].id)
}

output "api_security_group_id" {
  value = aws_security_group.api.id
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable in GitHub."
  value       = aws_iam_role.github_deploy.arn
}

output "elastic_password_secret" {
  description = "Secrets Manager secret holding the elastic user's password."
  value       = aws_secretsmanager_secret.elastic.name
}

output "github_repository_variables" {
  description = "Copy these into GitHub: Settings > Secrets and variables > Actions > Variables."
  value = {
    AWS_REGION            = var.aws_region
    AWS_DEPLOY_ROLE_ARN   = aws_iam_role.github_deploy.arn
    ECR_REPOSITORY        = aws_ecr_repository.api.name
    ECS_CLUSTER           = aws_ecs_cluster.main.name
    ECS_SERVICE           = aws_ecs_service.api.name
    ECS_TASK_FAMILY       = aws_ecs_task_definition.api.family
    PRIVATE_SUBNET_IDS    = join(",", aws_subnet.private[*].id)
    API_SECURITY_GROUP_ID = aws_security_group.api.id
  }
}
