#!/usr/bin/env bash
# Build, push, deploy and seed the API on AWS. Used by GitHub Actions and by
# the Makefile (make aws-deploy / make aws-seed), so both run the same steps.
#
# Required environment (the Terraform output github_repository_variables):
#   AWS_REGION ECR_REPOSITORY ECS_CLUSTER ECS_SERVICE ECS_TASK_FAMILY
#   PRIVATE_SUBNET_IDS API_SECURITY_GROUP_ID
# Optional: IMAGE_TAG (default: current git commit)
#
# Usage: scripts/aws.sh build-push | deploy | seed | all
set -euo pipefail

: "${AWS_REGION:?}" "${ECR_REPOSITORY:?}" "${ECS_CLUSTER:?}" "${ECS_SERVICE:?}" "${ECS_TASK_FAMILY:?}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

log() { printf '\n==> %s\n' "$*"; }

build_push() {
  log "Logging in to ECR ${REGISTRY}"
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
  log "Building ${IMAGE} (linux/amd64, models baked in)"
  docker build --platform linux/amd64 -f backend/Dockerfile \
    -t "$IMAGE" -t "${REGISTRY}/${ECR_REPOSITORY}:latest" .
  docker push "$IMAGE"
  docker push "${REGISTRY}/${ECR_REPOSITORY}:latest"
}

# Registers a new revision of the latest task definition with the new image,
# so environment/secrets changes made by Terraform are kept.
register_task_definition() {
  aws ecs describe-task-definition --region "$AWS_REGION" --task-definition "$ECS_TASK_FAMILY" \
    --query taskDefinition --output json \
  | jq --arg IMG "$IMAGE" '.containerDefinitions[0].image = $IMG
      | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities,
            .registeredAt, .registeredBy)' > /tmp/taskdef.json
  aws ecs register-task-definition --region "$AWS_REGION" --cli-input-json file:///tmp/taskdef.json \
    --query taskDefinition.taskDefinitionArn --output text
}

deploy() {
  log "Registering task definition for ${IMAGE}"
  TASK_DEF_ARN="$(register_task_definition)"
  echo "$TASK_DEF_ARN"
  log "Rolling ${ECS_SERVICE} (circuit breaker rolls back a failing image)"
  aws ecs update-service --region "$AWS_REGION" --cluster "$ECS_CLUSTER" --service "$ECS_SERVICE" \
    --task-definition "$TASK_DEF_ARN" --query service.serviceName --output text
  aws ecs wait services-stable --region "$AWS_REGION" --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE"
  log "Deployed ${IMAGE}"
}

seed() {
  : "${PRIVATE_SUBNET_IDS:?}" "${API_SECURITY_GROUP_ID:?}"
  log "Running the index build (python -m app.ingest) as a one-off Fargate task"
  TASK_ARN="$(aws ecs run-task --region "$AWS_REGION" --cluster "$ECS_CLUSTER" \
    --task-definition "$ECS_TASK_FAMILY" --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${PRIVATE_SUBNET_IDS}],securityGroups=[${API_SECURITY_GROUP_ID}],assignPublicIp=DISABLED}" \
    --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","app.ingest"]}]}' \
    --query 'tasks[0].taskArn' --output text)"
  echo "$TASK_ARN"
  aws ecs wait tasks-stopped --region "$AWS_REGION" --cluster "$ECS_CLUSTER" --tasks "$TASK_ARN"
  EXIT_CODE="$(aws ecs describe-tasks --region "$AWS_REGION" --cluster "$ECS_CLUSTER" --tasks "$TASK_ARN" \
    --query 'tasks[0].containers[0].exitCode' --output text)"
  if [ "$EXIT_CODE" != "0" ]; then
    echo "Seed task failed (exit code ${EXIT_CODE}); see CloudWatch log group /ecs/<prefix>/api" >&2
    exit 1
  fi
  log "Index built"
}

case "${1:-}" in
  build-push) build_push ;;
  deploy) deploy ;;
  seed) seed ;;
  all) build_push; deploy ;;
  *) echo "usage: $0 build-push|deploy|seed|all" >&2; exit 2 ;;
esac
