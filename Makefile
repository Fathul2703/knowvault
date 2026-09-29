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

.PHONY: up down logs invite-docker test-docker
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

# --- Local (no Docker for the apps; needs PostgreSQL) ---------------------------------

.PHONY: install migrate invite api worker web
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
