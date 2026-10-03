# Developer commands. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

# Loads .env (if present) into the environment of the command that follows.
LOAD_ENV := set -a; [ -f .env ] && source ./.env; set +a;

API := apps/api
WEB := apps/web

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env
	@echo "Created .env from .env.example"

# --- Docker Compose -------------------------------------------------------------------

.PHONY: up down logs invite-docker test-docker model-docker reindex-docker eval-docker \
	eval-answers-docker e2e
up: .env ## Start the full stack with Docker Compose
	docker compose up --build

down: ## Stop the stack (keeps the database volume)
	docker compose down

logs: ## Follow logs of all services
	docker compose logs -f

invite-docker: ## Create a registration invite inside the running api container
	docker compose exec api knowvault create-invite

test-docker: ## Run the API tests inside the api container
	docker compose exec api pytest

model-docker: ## Download the embedding model into the shared volume now
	docker compose exec api knowvault download-model

reindex-docker: ## Queue documents that still need (re-)embedding
	docker compose exec api knowvault reindex

EVAL_ARGS = --corpus /eval/corpus --dataset /eval/datasets/retrieval.jsonl --output-dir /eval/reports

eval-docker: ## Run the retrieval evaluation with the real model; report goes to eval/reports
	docker compose run --rm -v ./eval:/eval api knowvault eval-retrieval $(EVAL_ARGS)

ANSWER_EVAL_ARGS = $(EVAL_ARGS) --review-dir /eval/reviews

eval-answers-docker: ## Run the answer evaluation with LLM_PROVIDER from .env; reports in eval/
	docker compose run --rm -v ./eval:/eval api knowvault eval-answers $(ANSWER_EVAL_ARGS)

e2e: ## Browser end-to-end tests against a throwaway stack (compose.e2e.yaml, port 3100)
	docker compose -f compose.e2e.yaml up -d --build --wait
	cd $(WEB) && npx playwright install chromium && npm run e2e; \
		status=$$?; cd $(CURDIR) && docker compose -f compose.e2e.yaml down; exit $$status

# --- Local (no Docker for the apps; needs PostgreSQL) ---------------------------------

.PHONY: install migrate invite api worker web model reindex eval eval-answers
install: .env ## Install API and web dependencies
	cd $(API) && uv sync
	cd $(WEB) && npm ci

migrate: ## Apply database migrations
	$(LOAD_ENV) cd $(API) && uv run alembic upgrade head

invite: ## Create a registration invite
	$(LOAD_ENV) cd $(API) && uv run knowvault create-invite

api: ## Run the API with auto-reload on http://localhost:8000
	$(LOAD_ENV) cd $(API) && uv run uvicorn knowvault.main:create_app --factory --reload --reload-dir src --port 8000

worker: ## Run the document-processing worker
	$(LOAD_ENV) cd $(API) && uv run knowvault worker

model: ## Download the embedding model now instead of on first use
	$(LOAD_ENV) cd $(API) && uv run knowvault download-model

reindex: ## Queue documents that still need (re-)embedding
	$(LOAD_ENV) cd $(API) && uv run knowvault reindex

eval: ## Run the retrieval evaluation on your machine; report goes to eval/reports
	$(LOAD_ENV) cd $(API) && uv run knowvault eval-retrieval --corpus ../../eval/corpus \
		--dataset ../../eval/datasets/retrieval.jsonl --output-dir ../../eval/reports

eval-answers: ## Run the answer evaluation on your machine (LLM_PROVIDER from .env)
	$(LOAD_ENV) cd $(API) && uv run knowvault eval-answers --corpus ../../eval/corpus \
		--dataset ../../eval/datasets/retrieval.jsonl --output-dir ../../eval/reports \
		--review-dir ../../eval/reviews

web: ## Run the web app on http://localhost:3000
	$(LOAD_ENV) cd $(WEB) && npm run dev

# --- Quality ----------------------------------------------------------------------------

.PHONY: check lint typecheck test test-api test-web openapi
check: lint typecheck test ## Run every check that CI runs

lint: ## Lint and format-check both apps
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
	cd $(WEB) && npm run lint

typecheck: ## Type-check both apps
	cd $(API) && uv run mypy
	cd $(WEB) && npm run typecheck

test: test-api test-web ## Run all tests

test-api: ## Run API tests (needs TEST_DATABASE_URL)
	$(LOAD_ENV) cd $(API) && uv run pytest

test-web: ## Run web tests
	cd $(WEB) && npm test

openapi: ## Regenerate the OpenAPI schema and the web app's API types
	cd $(API) && uv run knowvault export-openapi > openapi.json
	cd $(WEB) && npm run generate:api
