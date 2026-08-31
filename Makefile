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
	@echo "inbox → http://localhost:8025   (sign-in mail lands here)"
	@trap 'kill 0' EXIT; \
	  ( cd $(API) && MODERATION_DEV_BYPASS=$${MODERATION_DEV_BYPASS:-true} \
	      SMTP_HOST=$${SMTP_HOST:-localhost} SMTP_PORT=$${SMTP_PORT:-1025} \
	      SMTP_START_TLS=$${SMTP_START_TLS:-false} \
	      RUN_SCHEDULER=$${RUN_SCHEDULER:-true} \
	      uv run uvicorn app.main:app --reload --port 8000 ) & \
	  ( cd $(WEB) && VITE_DEV_MAIL_INBOX=$${VITE_DEV_MAIL_INBOX:-http://localhost:8025} \
	      npm run dev ) & \
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
#
# A name may carry a feature-class filter, as `US:P`. The full US dump is 470MB,
# of which 381MB is half a million lakes and a quarter million hills nobody
# searches for; its populated places are 101MB and still include Boring, Oregon.
# This default is 744k places in 429MB, which is what the deployment runs.
GEONAMES ?= cities500 GB CA US:P

seed: migrate  ## Download and import real GeoNames data
	@cd $(API) && uv run python scripts/fetch_geonames.py $(GEONAMES)

seed-demo: seed  ## Add demo discoveries so the dev globe has pins
	@cd $(API) && uv run python scripts/seed_demo.py

migrate-remote:  ## Apply migrations to the deployment database (Supabase)
	@# Runs against DATABASE_URL_DIRECT, because Alembic needs prepared
	@# statements and Supabase's transaction pooler has none. Reads api/.env.
	@cd $(API) && SUPABASE_URL=$$(grep -E "^SUPABASE_DB_URL_DIRECT=" .env | cut -d= -f2-) ; \
	  SESSION_URL=$$(grep -E "^SUPABASE_DB_URL_SESSION=" .env | cut -d= -f2-) ; \
	  cd $(CURDIR)/$(API) && \
	  DATABASE_URL="$$SUPABASE_URL" DATABASE_URL_DIRECT="$$SUPABASE_URL" \
	    uv run alembic upgrade head \
	  || ( echo "direct connection failed (IPv6?), retrying via the session pooler" ; \
	       DATABASE_URL="$$SESSION_URL" DATABASE_URL_DIRECT="$$SESSION_URL" \
	         uv run alembic upgrade head )

migrate: up  ## Apply alembic migrations
	@cd $(API) && uv run alembic upgrade head

loadtest: up  ## Load profile for search and viewport (needs the API running)
	@cd $(API) && uv run locust -f loadtest/locustfile.py --headless \
	  --users 60 --spawn-rate 20 --run-time 30s --host http://localhost:8000 --only-summary

e2e:  ## Playwright end-to-end suite, including the accessibility audit
	@cd $(WEB) && npx playwright test

clean:  ## Remove build and cache artifacts
	@rm -rf $(WEB)/dist $(API)/.pytest_cache $(API)/.ruff_cache $(API)/.mypy_cache
