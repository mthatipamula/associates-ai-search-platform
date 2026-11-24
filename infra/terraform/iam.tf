# Least-privilege roles:
#   task_execution  - ECS pulls images, writes logs, injects secrets
#   api_task        - what the API code itself may call (Bedrock, only if enabled)
#   es_host         - the EC2 host: join ECS, attach its data volume

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- Task execution role -------------------------------------------------------

resource "aws_iam_role" "task_execution" {
  name               = "${local.prefix}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name = "read-app-secrets"
  role = aws_iam_role.task_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.elastic.arn]
    }]
  })
}

# --- API task role -------------------------------------------------------------

resource "aws_iam_role" "api_task" {
  name               = "${local.prefix}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "api_bedrock" {
  count = var.llm_provider == "bedrock" ? 1 : 0
  name  = "invoke-bedrock-models"
  role  = aws_iam_role.api_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "InvokeClaudeAndTitan"
      Effect = "Allow"
      Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = [
        "arn:${local.partition}:bedrock:*::foundation-model/anthropic.*",
        "arn:${local.partition}:bedrock:*::foundation-model/amazon.titan-embed-*",
        "arn:${local.partition}:bedrock:*:${local.account_id}:inference-profile/*",
      ]
    }]
  })
}

# --- Elasticsearch EC2 host ----------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "es_host" {
  name               = "${local.prefix}-es-host"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "es_host_ecs" {
  role       = aws_iam_role.es_host.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "es_host_ssm" {
  # Shell access through Session Manager instead of SSH keys / open ports.
  role       = aws_iam_role.es_host.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "es_host_attach_volume" {
  name = "attach-es-data-volume"
  role = aws_iam_role.es_host.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["ec2:AttachVolume"]
      Resource = [
        aws_ebs_volume.es_data.arn,
        "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:instance/*",
      ]
      Condition = {
        StringEquals = { "aws:ResourceTag/Project" = var.name }
      }
    }]
  })
}

resource "aws_iam_instance_profile" "es_host" {
  name = "${local.prefix}-es-host"
  role = aws_iam_role.es_host.name
}
