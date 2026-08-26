#!/usr/bin/env bash
# shared/kernel/version.json を作る。/info・システムステータス画面・entrypoint の
# 起動ログが「どのコミットのイメージが動いているか」を答えるための唯一の出どころ。
#
# 呼ばれる場所は 3 つ:
#   1. Komodo Build の pre_build（本番の経路）— クローン済みリポジトリで git から作り、
#      その出力が Docker ビルドコンテキストへ入る（ADR-0023）
#   2. Dockerfile の RUN — 1 が動いていれば **何もしない**。無ければ dev と刻む
#   3. 手元での確認（`make image` / 直接実行）
#
# 優先順位: **git > 既にある version.json > dev**
#
# ⚠ git が引ける場所では必ず作り直す。Komodo はビルドディレクトリを使い回し、
#   version.json は .gitignore 済みで `git pull` でも消えないため、「既存を尊重する」
#   にすると2回目以降のビルドが**初回の版を名乗り続ける**。
# ⚠ 逆にイメージの中（.git が無い）では既存を絶対に上書きしない。上書きにすると
#   pre_build が作った本物の版を Dockerfile の RUN が dev に潰す。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_ROOT/shared/kernel/version.json"

# --- 1. git から作る（引ける場所では必ず作り直す）-----------------------------
# ⚠ `-c safe.directory=*` が要る。Komodo の periphery はクローンした所有者と別 UID で
#   pre_build を走らせることがあり、無いと "dubious ownership" で git が黙って落ちる。
if command -v git >/dev/null 2>&1 && [ -d "$PROJECT_ROOT/.git" ]; then
    GIT=(git -c "safe.directory=*" --git-dir="$PROJECT_ROOT/.git" --work-tree="$PROJECT_ROOT")

    COMMIT_HASH=$("${GIT[@]}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    COMMIT_HASH_FULL=$("${GIT[@]}" rev-parse HEAD 2>/dev/null || echo "unknown")
    BRANCH=$("${GIT[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    COMMIT_DATE=$("${GIT[@]}" log -1 --format=%ci 2>/dev/null || echo "unknown")

    # detached HEAD（CI のチェックアウト等）では BRANCH が "HEAD" になる。
    # 呼び出し側がブランチ名を知っているなら BRANCH_OVERRIDE で補う。
    if [ -n "${BRANCH_OVERRIDE:-}" ] && { [ "$BRANCH" = "HEAD" ] || [ "$BRANCH" = "unknown" ]; }; then
        BRANCH="$BRANCH_OVERRIDE"
    fi

    if [ "$BRANCH" = "main" ]; then
        VERSION="v$COMMIT_HASH"
    else
        VERSION="v$COMMIT_HASH-$BRANCH"
    fi
    SOURCE="git"
elif [ -s "$VERSION_FILE" ] && grep -q '"commit_hash"' "$VERSION_FILE"; then
    # --- 2. git が無い＝イメージの中。ビルド前に置かれた内容が正 -----------------
    echo "[version] 既存の version.json を使います: $VERSION_FILE"
    cat "$VERSION_FILE"
    exit 0
else
    # --- 3. どちらでもない（`docker build` を素で叩いた等）----------------------
    COMMIT_HASH="dev"
    COMMIT_HASH_FULL="dev"
    BRANCH="unknown"
    COMMIT_DATE="unknown"
    VERSION="dev"
    SOURCE="default"
fi

BUILD_DATE=$(date -u -Iseconds)   # 契約: 時刻は UTC（HANDOVER §14）

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

echo "[version] $SOURCE から生成しました: $VERSION ($COMMIT_HASH, $BRANCH) → $VERSION_FILE"
