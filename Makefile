.PHONY: up seed eval test down logs kibana aws-init aws-plan aws-apply aws-deploy aws-seed aws-url aws-destroy

up:          ## start Elasticsearch + API (http://localhost:8000)
	docker compose up -d --build

seed:        ## (re)build the index from data/documents.jsonl with an alias swap
	docker compose exec api python -m app.ingest

eval:        ## relevance + latency evaluation (writes eval/results.md)
	docker compose exec api python /eval/evaluate.py --out /eval/results.md
	docker compose cp api:/eval/results.md eval/results.md

test:        ## unit tests (no Elasticsearch needed)
	docker compose exec -e EMBED_PROVIDER=hash api pytest -q -p no:cacheprovider tests

kibana:      ## optional Kibana on http://localhost:5601
	docker compose --profile kibana up -d kibana

logs:
	docker compose logs -f api

down:
	docker compose down

# --- AWS (see docs/aws-deployment.md) ------------------------------------------
TF := terraform -chdir=infra/terraform
# Deploy settings come straight from Terraform outputs.
AWS_ENV = $(shell $(TF) output -json github_repository_variables | jq -r 'to_entries[] | "\(.key)=\(.value)"')

aws-init:    ## terraform init with the S3 backend (needs infra/terraform/backend.hcl)
	$(TF) init -backend-config=backend.hcl

aws-plan:    ## show what would change in AWS
	$(TF) plan -out=tfplan

aws-apply:   ## create/update the AWS infrastructure from the saved plan
	$(TF) apply tfplan

aws-deploy:  ## build the image, push to ECR and roll the ECS service (same as CI)
	env $(AWS_ENV) scripts/aws.sh all

aws-seed:    ## build the search index in AWS (one-off Fargate task)
	env $(AWS_ENV) scripts/aws.sh seed

aws-url:     ## print the app URL
	@$(TF) output -raw app_url; echo

aws-destroy: ## delete everything Terraform created (stops all costs)
	$(TF) destroy
