# ===== frontend build stage =====
# Node / node_modules はビルドにしか使わないため、最終イメージには含めない。
FROM node:24-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ===== application image =====
FROM python:3.14-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2

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
#   CI（setup-uv の version）と同じ版に揃える。
# ⚠ **ghcr.io の像から COPY しない。** 像のビルドが GitHub に頼らないよう、
#   PyPI の wheel から入れる（task #172）。
# uv は依存を入れるときにしか使わないので、/tmp に入れて同じ RUN の中で消す
# （最終イメージに残さない）。
# renovate: datasource=pypi depName=uv
ARG UV_VERSION=0.12.5

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore \
      --target /tmp/uv "uv==${UV_VERSION}" \
    && /tmp/uv/bin/uv sync --frozen --no-dev --no-install-project \
    && rm -rf /tmp/uv

COPY . /app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:$PATH"

# バージョン情報（shared/kernel/version.json）は **ビルドの前に生成してコンテキストへ入れる**。
# build の「版を刻む」段が scripts/generate_version.sh を実行し、その出力がここへ
# COPY されてくる（ADR-0044）。この RUN は「無かったときに dev として印を付ける」だけで、
# 既にある内容は書き換えない。イメージには .git が入らないので、ここで git は引けない。
# ⚠ **ビルド情報を受け取る ARG を足さない。** 渡す側ごとに名前がずれて壊れた実績がある
#   （CLAUDE.md「ビルドとデプロイ」）。
RUN bash scripts/generate_version.sh

RUN chmod +x /app/scripts/entrypoint.sh
# 実行ユーザーの UID。置き場の所有者と揃える必要があるため、値を変えるときは
# deploy/k8s/10-storage.yaml の chown と 40-app.yaml の fsGroup も揃える。
ARG APP_UID=5678
RUN adduser -u "$APP_UID" --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# エントリポイントはイメージに焼き込む。compose は command でモードのみ指定する。
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
