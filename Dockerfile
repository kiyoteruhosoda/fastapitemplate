# ===== frontend build stage =====
# Node / node_modules are only needed for the build, so they are left out of the final image.
FROM node:24-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ===== application image =====
FROM python:3.15-slim@sha256:f786b2e19cf9bb54e96bfcd4c1b40c4c56336c22e60607ffd4b080ae5b5dee83

EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    curl \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# uv (dependency management). Dependencies get their own layer so the cache works.
# ⚠ Pin the version. With `:latest` the resolver version can change even for the same commit.
#   Keep it at the same version as CI (setup-uv's version).
# ⚠ **Do not COPY from the ghcr.io image.** Install from the PyPI wheel so the image build
#   doesn't depend on GitHub (task #172).
# uv is only needed to install dependencies, so put it in /tmp and delete it in the same RUN
# (it is not left in the final image).
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

# Version info (shared/kernel/version.json) is **generated before the build and put in the
# context**. The "stamp the version" stage of build runs scripts/generate_version.sh and its
# output is COPYed in here (ADR-0073 §1). This RUN only "marks it as dev if missing" and never
# rewrites existing content. The image has no .git, so git can't be queried here.
# ⚠ **Do not add ARGs that receive build info.** Names drifted per caller and broke things
#   before (CLAUDE.md "Build and deploy").
RUN bash scripts/generate_version.sh

RUN chmod +x /app/scripts/entrypoint.sh
# UID of the runtime user. It must match the owner of the storage, so when changing it also
# update the chown in deploy/k8s/10-storage.yaml and fsGroup in 40-app.yaml.
ARG APP_UID=5678
RUN adduser -u "$APP_UID" --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# The entrypoint is baked into the image. compose only selects the mode via command.
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
