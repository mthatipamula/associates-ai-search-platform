.PHONY: up seed eval test down logs kibana

up:          ## start Elasticsearch + API (http://localhost:8000)
	docker compose up -d --build

seed:        ## (re)build the index from data/documents.jsonl with an alias swap
	docker compose exec api python -m app.ingest

eval:        ## relevance + latency evaluation (writes eval/results.md)
	docker compose exec api python /eval/evaluate.py --out /eval/results.md
	docker compose cp api:/eval/results.md eval/results.md

test:        ## unit tests (no Elasticsearch needed)
	docker compose exec -e EMBED_PROVIDER=hash api pytest -q tests

kibana:      ## optional Kibana on http://localhost:5601
	docker compose --profile kibana up -d kibana

logs:
	docker compose logs -f api

down:
	docker compose down
