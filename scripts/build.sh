#!/usr/bin/env bash
# scripts/build.sh — ソース側でビルドする（デプロイ先とは別ホスト。ここでは起動しない）。
#
# Docker イメージ（app / db）をビルドし、tar ＋デプロイに必要な一式を
# 出力ディレクトリ（既定 dist/）へ書き出す。デプロイ先へは dist/ をディレクトリごと転送し、
# 中の deploy.sh を実行するだけでよい（レジストリ不要）。
#
# 使い方:
#   ./scripts/build.sh [出力DIR]              # 既定 dist/
#   PLATFORM=linux/amd64 ./scripts/build.sh   # クロスビルド（buildx がある場合のみ有効）
#
# 出力（＝デプロイバンドル）:
#   image.tar image-db.tar        ビルド済みイメージ（app / MariaDB）
#   deploy.sh                     デプロイ入口（app / migrate / reset すべてこれ 1 本）
#   .env.example                  設定テンプレート（deploy.sh が .env を生成）
#   manifest.env manifest.sha256  照合用メタデータ
#
# compose / nginx 設定はイメージに焼き込まれており、deploy.sh がロード後に取り出して
# 配置先を常にイメージと同じ版へ同期する（dist へは同梱しない）。
#
# 前提: docker。
set -euo pipefail

log() { printf '[fastapitemplate] %s\n' "$*" >&2; }
die() { printf '[fastapitemplate][error] %s\n' "$*" >&2; exit 1; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

out_dir="dist"
case "${1:-}" in
  -h | --help) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") ;;
  *) out_dir="$1" ;;
esac

command -v docker >/dev/null 2>&1 || die "docker が見つかりません。"

app_name="fastapitemplate"
git_commit="$(git rev-parse HEAD 2>/dev/null || printf unknown)"
git_commit_short="$(git rev-parse --short HEAD 2>/dev/null || printf unknown)"
git_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)"
git_commit_date="$(git log -1 --format=%ci 2>/dev/null || printf unknown)"
build_date="$(date -Iseconds)"
version="${IMAGE_TAG:-latest}"

app_ref="${app_name}:${version}"
db_ref="${app_name}-db:${version}"

# PLATFORM が指定され buildx が使えるときだけクロスビルドする。無指定なら実行ホストの
# ネイティブアーキテクチャでビルドする（dev コンテナ＝デプロイ先と同アーキの想定）。
build_image() {
  local ref="$1"; shift
  if [[ -n "${PLATFORM:-}" ]]; then
    docker buildx version >/dev/null 2>&1 || die "PLATFORM=$PLATFORM が指定されましたが buildx がありません。"
    docker buildx build --platform "$PLATFORM" --load -t "$ref" "$@"
  else
    docker build -t "$ref" "$@"
  fi
}

log "イメージをビルドします: $app_ref（commit=$git_commit_short branch=$git_branch）..."
build_image "$app_ref" \
  --build-arg "COMMIT_HASH=$git_commit_short" \
  --build-arg "COMMIT_HASH_FULL=$git_commit" \
  --build-arg "BRANCH=$git_branch" \
  --build-arg "COMMIT_DATE=$git_commit_date" \
  --build-arg "BUILD_DATE=$build_date" \
  --label "org.opencontainers.image.revision=$git_commit" \
  --label "org.opencontainers.image.version=$version" \
  -f Dockerfile .

log "イメージをビルドします: $db_ref ..."
build_image "$db_ref" \
  --label "org.opencontainers.image.revision=$git_commit" \
  --label "org.opencontainers.image.version=$version" \
  ./db

# --- デプロイバンドル出力 --------------------------------------------------------
mkdir -p "$out_dir"
manifest="$out_dir/manifest.sha256"
: >"$manifest"

write_manifest_kv() {
  local key="$1" value="$2" quoted
  printf -v quoted '%q' "$value"
  printf '%s=%s\n' "$key" "$quoted"
}

{
  write_manifest_kv commit "$git_commit"
  write_manifest_kv branch "$git_branch"
  write_manifest_kv version "$version"
  write_manifest_kv build_date "$build_date"
} >"$out_dir/manifest.env"

save_image() {
  local ref="$1" tar="$2" key="$3" image_id
  image_id="$(docker image inspect -f '{{.Id}}' "$ref")"
  log "保存します: $ref → $tar ..."
  docker save "$ref" -o "$tar"
  chmod 644 "$tar"
  (cd "$out_dir" && sha256sum "$(basename "$tar")") >>"$manifest"
  {
    write_manifest_kv "${key}_ref" "$ref"
    write_manifest_kv "${key}_image_id" "$image_id"
  } >>"$out_dir/manifest.env"
}

save_image "$app_ref" "$out_dir/image.tar" app
save_image "$db_ref" "$out_dir/image-db.tar" db

cp "$repo_root/.env.example" "$out_dir/.env.example"
cp "$repo_root/scripts/deploy.sh" "$out_dir/deploy.sh"
chmod +x "$out_dir/deploy.sh"

log "完了。$out_dir/ をデプロイ先の <app>/<stg|prod>/ へ転送し、./deploy.sh <app|migrate|reset> を実行してください。"
