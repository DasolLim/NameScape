SHELL := /bin/bash
API := api
WEB := web
COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: help vm up down dev verify test typecheck lint migrate gen-types e2e clean

help:  ## List targets
	@grep -hE '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t20

vm:
	@colima status >/dev/null 2>&1 || { echo "starting colima..."; colima start; }

up: vm  ## Start postgres and redis
	@$(COMPOSE) up -d --wait

down:  ## Stop postgres and redis
	@$(COMPOSE) down

# Local development has no Anthropic key, and moderation fails closed without
# one, so nothing could be claimed or proposed. Development only.
dev: up  ## Run the API and web dev servers
	@echo "api → http://localhost:8000   web → http://localhost:5173"
	@trap 'kill 0' EXIT; \
	  ( cd $(API) && MODERATION_DEV_BYPASS=$${MODERATION_DEV_BYPASS:-true} \
	      uv run uvicorn app.main:app --reload --port 8000 ) & \
	  ( cd $(WEB) && npm run dev ) & \
	  wait

typecheck:  ## mypy strict + tsc
	@cd $(API) && uv run mypy
	@cd $(WEB) && npm run --silent typecheck

lint:  ## ruff + eslint
	@cd $(API) && uv run ruff check . && uv run ruff format --check .
	@cd $(WEB) && npm run --silent lint

test:  ## pytest + vitest
	@cd $(API) && uv run pytest -q
	@cd $(WEB) && npm run --silent test

verify: up  ## Typecheck, lint, and test everything; stops at the first failure
	@set -e; \
	  cd $(API) && uv run mypy && uv run ruff check . && uv run ruff format --check . && uv run pytest -q && \
	  cd ../$(WEB) && npm run --silent typecheck && npm run --silent lint && npm run --silent test

gen-types:  ## Regenerate web/src/api/schema.ts from the API's OpenAPI schema
	@cd $(API) && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > ../$(WEB)/openapi.json
	@cd $(WEB) && npx --yes openapi-typescript openapi.json -o src/api/schema.ts >/dev/null && rm openapi.json
	@echo "generated $(WEB)/src/api/schema.ts"

# Real GeoNames data, not the test fixture: the fixture's ids are
# illustrative and collide with real ones. GEONAMES overrides the selection,
# e.g. `make seed GEONAMES="cities500 US GB CA"`.
GEONAMES ?= cities500 GB CA US

seed: migrate  ## Download and import real GeoNames data
	@cd $(API) && uv run python scripts/fetch_geonames.py $(GEONAMES)

seed-demo: seed  ## Add demo discoveries so the dev globe has pins
	@cd $(API) && uv run python scripts/seed_demo.py

migrate: up  ## Apply alembic migrations
	@cd $(API) && uv run alembic upgrade head

loadtest: up  ## Load profile for search and viewport (needs the API running)
	@cd $(API) && uv run locust -f loadtest/locustfile.py --headless \
	  --users 60 --spawn-rate 20 --run-time 30s --host http://localhost:8000 --only-summary

e2e:  ## Playwright end-to-end suite, including the accessibility audit
	@cd $(WEB) && npx playwright test

clean:  ## Remove build and cache artifacts
	@rm -rf $(WEB)/dist $(API)/.pytest_cache $(API)/.ruff_cache $(API)/.mypy_cache
