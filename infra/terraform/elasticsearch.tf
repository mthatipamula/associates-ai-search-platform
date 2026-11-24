# Self-managed Elasticsearch: one ECS task on one EC2 instance, data on a
# separate encrypted EBS volume.
#
# Why EC2 and not Fargate: Elasticsearch needs vm.max_map_count raised on the
# host and fast persistent disk; neither fits Fargate well.
#
# Durability: the data volume outlives the instance. If the Auto Scaling group
# replaces the instance, the new one re-attaches the same volume at boot. The
# index can also always be rebuilt from source (the seed task), which is the
# real recovery path: search indices are derived data.
#
# Production: run 3 nodes across AZs (or Elastic Cloud on AWS / ECK), take
# snapshots to S3 with the repository-s3 plugin, and turn on TLS.

data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"
}

resource "aws_ebs_volume" "es_data" {
  availability_zone = local.azs[0] # the instance is pinned to this AZ
  size              = var.es_data_volume_gb
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${local.prefix}-es-data" }

  lifecycle {
    prevent_destroy = false # set true for anything you care about
  }
}

resource "aws_security_group" "es_host" {
  name        = "${local.prefix}-es-host"
  description = "Elasticsearch EC2 host (no inbound; tasks use their own ENI)"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_egress_rule" "es_host_all" {
  security_group_id = aws_security_group.es_host.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_launch_template" "es" {
  name_prefix   = "${local.prefix}-es-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.es_instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.es_host.arn
  }
  vpc_security_group_ids = [aws_security_group.es_host.id]

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = 30
      volume_type = "gp3"
      encrypted   = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/templates/es_host_user_data.sh.tftpl", {
    cluster_name = aws_ecs_cluster.main.name
    volume_id    = aws_ebs_volume.es_data.id
    region       = var.aws_region
  }))

  # Provider default_tags do not reach instances launched by the ASG; the
  # Project tag is required by the attach-volume IAM condition.
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${local.prefix}-es-host", Project = var.name }
  }
}

resource "aws_autoscaling_group" "es" {
  name                = "${local.prefix}-es"
  min_size            = 1
  max_size            = 1
  desired_capacity    = 1
  vpc_zone_identifier = [aws_subnet.private[0].id] # same AZ as the data volume
  health_check_type   = "EC2"

  launch_template {
    id      = aws_launch_template.es.id
    version = aws_launch_template.es.latest_version
  }

  instance_refresh {
    strategy = "Rolling"
    preferences { min_healthy_percentage = 0 }
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }
}

resource "aws_ecs_capacity_provider" "es" {
  name = "${local.prefix}-es"
  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.es.arn
    managed_scaling {
      status = "DISABLED" # fixed single node
    }
    managed_termination_protection = "DISABLED"
  }
}

resource "aws_ecs_task_definition" "es" {
  family                   = "${local.prefix}-elasticsearch"
  requires_compatibilities = ["EC2"]
  network_mode             = "awsvpc"
  execution_role_arn       = aws_iam_role.task_execution.arn

  volume {
    name      = "esdata"
    host_path = "/esdata"
  }

  container_definitions = jsonencode([{
    name         = "elasticsearch"
    image        = var.es_image
    essential    = true
    memory       = var.es_container_memory
    portMappings = [{ containerPort = 9200, protocol = "tcp" }]
    environment = [
      { name = "discovery.type", value = "single-node" },
      { name = "ES_JAVA_OPTS", value = "-Xms${var.es_heap} -Xmx${var.es_heap}" },
      { name = "xpack.security.enabled", value = "true" },
      # Single node inside a private subnet: basic auth over HTTP. Turn on
      # xpack.security.http.ssl (or put TLS in front) for production.
      { name = "xpack.security.http.ssl.enabled", value = "false" },
      { name = "bootstrap.memory_lock", value = "false" },
    ]
    secrets     = [{ name = "ELASTIC_PASSWORD", valueFrom = aws_secretsmanager_secret.elastic.arn }]
    mountPoints = [{ sourceVolume = "esdata", containerPath = "/usr/share/elasticsearch/data" }]
    ulimits     = [{ name = "nofile", softLimit = 65535, hardLimit = 65535 }]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -fs -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5s' || exit 1"]
      interval    = 15
      timeout     = 10
      retries     = 10
      startPeriod = 90
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.es.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "es"
      }
    }
  }])
}

resource "aws_service_discovery_service" "es" {
  name = "elasticsearch"
  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.main.id
    routing_policy = "MULTIVALUE"
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
  # Lets ECS report task health to Cloud Map (failure threshold is fixed at 1).
  health_check_custom_config {}
}

resource "aws_ecs_service" "es" {
  name            = "elasticsearch"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.es.arn
  desired_count   = 1

  # Only one node fits on the host: stop the old task before starting a new one.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.es.name
    weight            = 1
  }

  # Only place Elasticsearch on a host whose data volume is mounted
  # (the user data sets this attribute after mounting /esdata).
  placement_constraints {
    type       = "memberOf"
    expression = "attribute:esdata == mounted"
  }

  network_configuration {
    subnets         = [aws_subnet.private[0].id]
    security_groups = [aws_security_group.es.id]
  }

  service_registries {
    registry_arn = aws_service_discovery_service.es.arn
  }

  depends_on = [aws_ecs_cluster_capacity_providers.main]
}
