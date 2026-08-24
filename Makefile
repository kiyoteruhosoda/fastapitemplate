# ================================
# fastapitemplate Makefile
# ================================

.PHONY: image \
	check check-backend check-frontend \
	format format-backend format-frontend \
	lint typecheck test \
	lint-frontend typecheck-frontend test-frontend

# --------------------------------
# イメージ（手元での確認用）
# --------------------------------
# 本番の成果物は Komodo Build が焼いてレジストリへ push する（ADR-0023）。
# ここで作るのは Dockerfile が壊れていないかを手元で確かめるためのもの。
IMAGE ?= fastapitemplate:dev

image:
	bash scripts/generate_version.sh
	docker build -t $(IMAGE) .

# --------------------------------
# 品質ゲート（CI と同じ順序・同じコマンドを流す）
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

# 個別に回したいとき
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

# --------------------------------
# 自動整形（コミット前に流す）
# --------------------------------

format: format-backend format-frontend

format-backend:
	uv run ruff format .
	uv run ruff check . --fix

format-frontend:
	cd frontend && npm run format
