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
# ⚠ 版を固定する。`:latest` だと同じコミットからでも解決器の版が変わりうる。
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . /app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:$PATH"

# バージョン情報（shared/kernel/version.json）は **ビルドの前に生成してコンテキストへ入れる**。
# Komodo Build の pre_build が scripts/generate_version.sh を実行し、その出力がここへ
# COPY されてくる（ADR-0023）。この RUN は「無かったときに dev として印を付ける」だけで、
# 既にある内容は書き換えない。イメージには .git が入らないので、ここで git は引けない。
RUN bash scripts/generate_version.sh

RUN chmod +x /app/scripts/entrypoint.sh
# 実行ユーザーの UID。データディレクトリの所有者（compose の init-paths）と揃える必要が
# あるため、値を変えるときは deploy/komodo/stack.toml の APP_UID / APP_GID も揃える。
ARG APP_UID=5678
RUN adduser -u "$APP_UID" --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# エントリポイントはイメージに焼き込む。compose は command でモードのみ指定する。
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
