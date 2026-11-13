# ================================
# fastapitemplate Makefile
# ================================

.PHONY: image \
	check check-backend check-frontend \
	format format-backend format-frontend \
	lint typecheck test \
	lint-frontend typecheck-frontend test-frontend test-e2e

# --------------------------------
# Image (for local checks)
# --------------------------------
# The production artifact is built by build inside the LAN and pushed to the registry
# (ADR-0073 §1). This one is only for checking locally that the Dockerfile isn't broken.
IMAGE ?= fastapitemplate:dev

image:
	bash scripts/generate_version.sh
	docker build -t $(IMAGE) .

# --------------------------------
# Quality gates (same order and commands as CI)
# --------------------------------

check: check-backend check-frontend

check-backend:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest

check-frontend:
	cd frontend && npm run format:check
	cd frontend && npm run lint
	cd frontend && npm run type-check
	cd frontend && npm run test

# To run them individually
lint:
	uv run ruff check .

typecheck:
	uv run mypy

test:
	uv run pytest

lint-frontend:
	cd frontend && npm run lint

typecheck-frontend:
	cd frontend && npm run type-check

test-frontend:
	cd frontend && npm run test

# Real-browser E2E (ADR-0072 §6). Heavy, so not part of check
test-e2e:
	cd frontend && npm run test:e2e

# --------------------------------
# Auto-format (run before committing)
# --------------------------------

format: format-backend format-frontend

format-backend:
	uv run ruff format .
	uv run ruff check . --fix

format-frontend:
	cd frontend && npm run format
