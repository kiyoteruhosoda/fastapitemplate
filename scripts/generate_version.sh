#!/usr/bin/env bash
# Creates shared/kernel/version.json, the single source that /info, the system status screen and
# the entrypoint's startup log use to answer "which commit's image is running".
#
# Called from three places:
#   1. build's "stamp the version" stage (production path) — generated from git in the cloned
#      repo; the output goes into the Docker build context (ADR-0073 §1)
#   2. RUN in the Dockerfile — does **nothing** if 1 ran; otherwise stamps dev
#   3. Local checks (`make image` / running it directly)
#
# Precedence: **git > existing version.json > dev**
#
# ⚠ Always regenerate where git is available. The build directory is reused (and version.json
#   is gitignored, so `git pull` doesn't remove it); if we "respected the existing file", every
#   build after the first would **keep reporting the first build's version**.
# ⚠ Conversely, inside the image (no .git) never overwrite the existing file. Otherwise the
#   Dockerfile's RUN would clobber the real version from pre_build with dev.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_ROOT/shared/kernel/version.json"

# --- 1. Generate from git (always regenerate where available) -----------------
# ⚠ `-c safe.directory=*` is required. The builder may run as a different UID than the clone's
#   owner, and without it git silently fails with "dubious ownership".
if command -v git >/dev/null 2>&1 && [ -d "$PROJECT_ROOT/.git" ]; then
    GIT=(git -c "safe.directory=*" --git-dir="$PROJECT_ROOT/.git" --work-tree="$PROJECT_ROOT")

    COMMIT_HASH=$("${GIT[@]}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    COMMIT_HASH_FULL=$("${GIT[@]}" rev-parse HEAD 2>/dev/null || echo "unknown")
    BRANCH=$("${GIT[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    COMMIT_DATE=$("${GIT[@]}" log -1 --format=%ci 2>/dev/null || echo "unknown")

    # On a detached HEAD (CI checkouts etc.) BRANCH becomes "HEAD".
    # If the caller knows the branch name, it supplies it via BRANCH_OVERRIDE.
    if [ -n "${BRANCH_OVERRIDE:-}" ] && { [ "$BRANCH" = "HEAD" ] || [ "$BRANCH" = "unknown" ]; }; then
        BRANCH="$BRANCH_OVERRIDE"
    fi

    # ⚠ No `v` prefix. This is a short commit hash, not a meaningful version (v1.2.3); with a
    #   `v` it would read as "such a release exists".
    if [ "$BRANCH" = "main" ]; then
        VERSION="$COMMIT_HASH"
    else
        VERSION="$COMMIT_HASH-$BRANCH"
    fi
    SOURCE="git"
elif [ -s "$VERSION_FILE" ] && grep -q '"commit_hash"' "$VERSION_FILE"; then
    # --- 2. No git = inside the image. What was placed before the build wins ------
    echo "[version] Using existing version.json: $VERSION_FILE"
    cat "$VERSION_FILE"
    exit 0
else
    # --- 3. Neither (e.g. a plain `docker build`) --------------------------------
    COMMIT_HASH="dev"
    COMMIT_HASH_FULL="dev"
    BRANCH="unknown"
    COMMIT_DATE="unknown"
    VERSION="dev"
    SOURCE="default"
fi

BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # Contract: times are UTC with a trailing Z (HANDOVER §14)

mkdir -p "$(dirname "$VERSION_FILE")"
cat > "$VERSION_FILE" << JSON
{
  "version": "$VERSION",
  "commit_hash": "$COMMIT_HASH",
  "commit_hash_full": "$COMMIT_HASH_FULL",
  "branch": "$BRANCH",
  "commit_date": "$COMMIT_DATE",
  "build_date": "$BUILD_DATE"
}
JSON

echo "[version] Generated from $SOURCE: $VERSION ($COMMIT_HASH, $BRANCH) → $VERSION_FILE"
