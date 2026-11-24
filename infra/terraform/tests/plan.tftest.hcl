# Offline plan test with a mocked AWS provider: no credentials, nothing created.
# Run: terraform -chdir=infra/terraform test

mock_provider "aws" {
  override_data {
    target = data.aws_availability_zones.available
    values = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  override_data {
    target = data.aws_partition.current
    values = { partition = "aws" }
  }
  override_data {
    target = data.aws_ssm_parameter.ecs_ami
    values = { value = "ami-0123456789abcdef0" }
  }
  override_data {
    target = data.aws_iam_policy_document.ecs_tasks_assume
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.ec2_assume
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  override_data {
    target = data.aws_iam_policy_document.github_assume
    values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

mock_provider "random" {}

variables {
  allowed_ingress_cidrs = ["203.0.113.7/32"]
}

run "plan_defaults" {
  command = plan

  assert {
    condition     = length(aws_subnet.private) == 2 && length(aws_subnet.public) == 2
    error_message = "Expected two public and two private subnets."
  }
  assert {
    condition     = keys(aws_vpc_security_group_ingress_rule.alb_http) == ["203.0.113.7/32"]
    error_message = "The load balancer must only admit the allow-listed CIDRs."
  }
  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.alb_https) == 0 && length(aws_lb_listener.https) == 0
    error_message = "No HTTPS listener without a certificate."
  }
  assert {
    condition     = aws_ecs_service.api.network_configuration[0].assign_public_ip == false
    error_message = "API tasks must not get public IPs."
  }
  assert {
    condition     = aws_ebs_volume.es_data.encrypted && aws_ebs_volume.es_data.availability_zone == "us-east-1a"
    error_message = "Elasticsearch data volume must be encrypted and in the host's AZ."
  }
  assert {
    condition     = length(aws_iam_role_policy.api_bedrock) == 0
    error_message = "No Bedrock permissions unless llm_provider = bedrock."
  }
  assert {
    condition     = aws_launch_template.es.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 must be enforced on the Elasticsearch host."
  }
}

run "plan_with_https_and_bedrock" {
  command = plan

  variables {
    certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/abc"
    llm_provider    = "bedrock"
  }

  assert {
    condition     = length(aws_lb_listener.https) == 1 && length(aws_vpc_security_group_ingress_rule.alb_https) == 1
    error_message = "HTTPS listener and rule expected when a certificate is set."
  }
  assert {
    condition     = aws_lb_listener.http.default_action[0].type == "redirect"
    error_message = "HTTP should redirect to HTTPS when a certificate is set."
  }
  assert {
    condition     = length(aws_iam_role_policy.api_bedrock) == 1
    error_message = "Bedrock policy expected when llm_provider = bedrock."
  }
}

run "rejects_open_ingress_by_omission" {
  command = plan
  variables {
    allowed_ingress_cidrs = []
  }
  expect_failures = [var.allowed_ingress_cidrs]
}
