# ===== frontend build stage =====
# Node / node_modules はビルドにしか使わないため、最終イメージには含めない。
FROM node:24-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ===== application image =====
FROM python:3.12-slim

EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    curl \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# uv（依存管理）。依存レイヤーを分けてキャッシュを効かせる。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . /app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:$PATH"

# Makefile から渡されるビルド情報で version.json を生成
ARG COMMIT_HASH=dev
ARG COMMIT_HASH_FULL=dev
ARG BRANCH=unknown
ARG COMMIT_DATE=unknown
ARG BUILD_DATE=unknown

RUN if [ "$BRANCH" = "main" ]; then VERSION="v${COMMIT_HASH}"; else VERSION="v${COMMIT_HASH}-${BRANCH}"; fi && \
    printf '{\n  "version": "%s",\n  "commit_hash": "%s",\n  "commit_hash_full": "%s",\n  "branch": "%s",\n  "commit_date": "%s",\n  "build_date": "%s"\n}\n' \
      "$VERSION" "$COMMIT_HASH" "$COMMIT_HASH_FULL" "$BRANCH" "$COMMIT_DATE" "$BUILD_DATE" \
    > shared/kernel/version.json

RUN chmod +x /app/scripts/entrypoint.sh
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# エントリポイントはイメージに焼き込む。compose は command でモードのみ指定する。
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
