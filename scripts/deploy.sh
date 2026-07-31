#!/bin/bash
# デプロイスクリプト（stg / prod 共通・配置ディレクトリから環境を自動判定）
#
# 配置想定（環境ごとに自己完結したディレクトリ。<app>/ 配下に stg/ と prod/ を置き、
# scripts/build.sh が出力した dist/ の中身をそのまま展開する）:
#   <app>/
#     stg/
#       image.tar          # ビルド済みアプリイメージ
#       image-db.tar       # DB イメージ（reset 時のみ使用）
#       deploy.sh          # このスクリプト（dist/deploy.sh を配置）
#       manifest.env       # ビルドメタデータ（commit・イメージ ID）
#       manifest.sha256    # tar の checksum（配置時の転送破損検出）
#       .env               # stg 用設定（無ければ初回デプロイ時にテンプレートを自動生成）
#       docker-compose.yml # stg 用（デプロイ時にイメージ内のコピーで自動更新される）
#       mnt/               # コンテナマウント用データ（data/ と db_data/ が作られる）
#     prod/                # 上記と同じ構成
#
# 使い方（モード引数は必須。<app>/<stg|prod>/ で実行する）:
#   ./deploy.sh app      # 通常デプロイ（アプリのみ更新。DBスキーマ変更なし）
#   ./deploy.sh migrate  # DDL更新時（新しい Alembic migration を追加した場合）
#   ./deploy.sh reset    # 完全初期化（DB・データ消去。破壊的）
#
# 環境変数（任意）:
#   APP_WEB_HOST_PORT  WEB 公開ポートの既定値。`.env` を新規生成するときの WEB_HOST_PORT に
#                      なる（既存の `.env` の値が正本なのでそちらが優先。ADR-0008）。
#                      build-remote-container.sh から自動で引き継がれる。
#
# デプロイ中にエラーが発生した場合は、失敗したモジュール（コンテナ）のログを
# 出力して終了する。

set -Eeuo pipefail

APP_NAME="fastapitemplate"

# 配置は dist/ をそのまま展開した形（<env>/deploy.sh）のみ。環境ディレクトリ直下で動く。
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="$(basename "$BASE_DIR")"

# ===== 環境判定（配置ディレクトリ名で stg / prod を切り替える） =====
# ENV_KIND（stg / prod）が分類の正。以降の分岐は ENV_NAME の字面ではなく ENV_KIND で行う
# （staging・*-stg 等のエイリアスに prod 既定値を適用してしまわないため）。
case "$ENV_NAME" in
  stg | staging | *-stg | *-staging)
    ENV_KIND=stg
    PROJECT="${APP_NAME}-stg"
    DEFAULT_WEB_HOST_PORT=8081
    DEFAULT_DB_CONTAINER="${APP_NAME}-mariadb-stg"
    DEFAULT_NETWORK="${APP_NAME}-stg"
    ;;
  prod | production | *-prod | *-production)
    ENV_KIND=prod
    PROJECT="${APP_NAME}"
    DEFAULT_WEB_HOST_PORT=8080
    DEFAULT_DB_CONTAINER="${APP_NAME}-mariadb"
    DEFAULT_NETWORK="${APP_NAME}-prod"
    ;;
  *)
    echo "[deploy][error] このスクリプトは ${APP_NAME}/<stg|prod>/ 配下に配置して実行してください。" >&2
    echo "  現在の配置: $BASE_DIR（環境ディレクトリ名 '$ENV_NAME' が stg / prod 系ではありません）" >&2
    exit 1
    ;;
esac

TAG="[deploy:$ENV_NAME]"
log()  { echo -e "\033[36m${TAG}\033[0m $*"; }
warn() { echo -e "\033[33m${TAG}[warn]\033[0m $*" >&2; }
err()  { echo -e "\033[31m${TAG}[error]\033[0m $*" >&2; }

# WEB 公開ポートとして使える値か（1〜65535 の整数）。先頭 0 を許すと算術評価が 8 進数として
# 解釈するため `^[1-9][0-9]{0,4}$` に限定する（`&&` の短絡で非数値は算術評価へ渡らない）。
is_valid_web_port() {
  [[ "$1" =~ ^[1-9][0-9]{0,4}$ ]] && (($1 <= 65535))
}

APP_IMAGE="${APP_NAME}:$ENV_NAME"
DB_IMAGE="${APP_NAME}-db:$ENV_NAME"
# `.env` を読む前の暫定値（診断がこれより前で走っても未定義にならないようにする）。
# `.env` 生成後に compose と同じ規則で解き直す。
DB_CONTAINER_NAME="$DEFAULT_DB_CONTAINER"
IMAGE_TAR="$BASE_DIR/image.tar"
IMAGE_DB_TAR="$BASE_DIR/image-db.tar"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
ENV_FILE="$BASE_DIR/.env"
MANIFEST_ENV="$BASE_DIR/manifest.env"
MANIFEST_SHA="$BASE_DIR/manifest.sha256"

# ===== manifest（build.sh の出力メタデータ。無ければ従来どおり動く） =====
# ロード時タグ・イメージ ID・commit を manifest から取り、配置物とビルド成果の齟齬を検出する。
LOADED_APP_REF="${APP_NAME}:latest"
LOADED_DB_REF="${APP_NAME}-db:latest"
MANIFEST_APP_IMAGE_ID=""
MANIFEST_DB_IMAGE_ID=""
MANIFEST_COMMIT=""
if [ -f "$MANIFEST_ENV" ]; then
  # shellcheck disable=SC1090
  . "$MANIFEST_ENV"
  LOADED_APP_REF="${app_ref:-$LOADED_APP_REF}"
  LOADED_DB_REF="${db_ref:-$LOADED_DB_REF}"
  MANIFEST_APP_IMAGE_ID="${app_image_id:-}"
  MANIFEST_DB_IMAGE_ID="${db_image_id:-}"
  MANIFEST_COMMIT="${commit:-}"
fi

# tar が manifest.sha256 の checksum と一致するか検証する（転送破損の早期検出）。
# manifest が無い・sha256sum が無い・該当エントリが無い場合は従来どおりスキップする。
verify_tar_checksum() { # 引数: tar のファイル名（BASE_DIR 直下）
  local name="$1"
  [ -f "$MANIFEST_SHA" ] || return 0
  command -v sha256sum >/dev/null 2>&1 || return 0
  grep -qE "  ${name}\$" "$MANIFEST_SHA" || return 0
  ( cd "$BASE_DIR" && grep -E "  ${name}\$" "$MANIFEST_SHA" | sha256sum -c - >/dev/null 2>&1 ) \
    || return 1
  return 0
}

# ロード済みイメージが manifest のイメージ ID と一致していれば docker load を省略できる。
image_matches_manifest() { # 引数: <イメージ参照> <期待イメージID>
  local ref="$1" expected="$2" actual
  [ -n "$expected" ] || return 1
  actual="$(docker image inspect -f '{{.Id}}' "$ref" 2>/dev/null || true)"
  [ -n "$actual" ] && [ "$actual" = "$expected" ]
}

# ===== .env の値を読む（compose interpolation と同じく「最後の定義」を採用） =====
# CR と前後の空白は必ず除去する（CR が残るとバインドマウント失敗の原因になる）。
env_file_value() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d'=' -f2- \
    | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' || true
}

# マウントルート。既定は環境ディレクトリ配下の mnt/（.env の HOST_DATA_ROOT で上書き可）。
HOST_DATA_ROOT="$(env_file_value HOST_DATA_ROOT)"
HOST_DATA_ROOT="${HOST_DATA_ROOT:-$BASE_DIR/mnt}"
DATA_PATH="$HOST_DATA_ROOT/data"
DB_PATH="$HOST_DATA_ROOT/db_data"

# WEB 公開ポート。優先順位は `.env` ＞ APP_WEB_HOST_PORT（build-remote-container.env からの
# 引き継ぎ）＞ 環境ディレクトリ名由来の既定値（ADR-0008）。
# APP_WEB_HOST_PORT の検証は**その値が実際に選ばれたときだけ**行う。`.env` が正本なので、
# 使われもしない古い・打ち間違えた値でデプロイを止めてはならない（不一致は警告で知らせる）。
WEB_HOST_PORT="$(env_file_value WEB_HOST_PORT)"
if [ -n "$WEB_HOST_PORT" ]; then
  WEB_HOST_PORT_SOURCE=".env"
  if [ -n "${APP_WEB_HOST_PORT:-}" ] && [ "$APP_WEB_HOST_PORT" != "$WEB_HOST_PORT" ]; then
    warn "APP_WEB_HOST_PORT=$APP_WEB_HOST_PORT is ignored; $ENV_FILE の WEB_HOST_PORT=$WEB_HOST_PORT が優先されます。"
    warn "  ポートを変えるには .env を編集してください（deploy は既存の .env を書き換えません）。"
  fi
elif [ -n "${APP_WEB_HOST_PORT:-}" ]; then
  if ! is_valid_web_port "$APP_WEB_HOST_PORT"; then
    err "APP_WEB_HOST_PORT must be an integer in 1-65535: $APP_WEB_HOST_PORT"
    exit 1
  fi
  WEB_HOST_PORT="$APP_WEB_HOST_PORT"
  WEB_HOST_PORT_SOURCE="APP_WEB_HOST_PORT"
else
  WEB_HOST_PORT="$DEFAULT_WEB_HOST_PORT"
  WEB_HOST_PORT_SOURCE="default (env: $ENV_KIND)"
fi
HEALTH_URL="http://127.0.0.1:${WEB_HOST_PORT}/healthz"

# compose interpolation はシェル環境変数 > --env-file の優先順位のため、ここで
# export した値が優先される。stg / prod が同一ホストでイメージを取り合わないよう
# 環境別タグに統一する。
export HOST_DATA_ROOT
export WEB_IMAGE="$APP_IMAGE"
export DB_IMAGE
# WEB_HOST_PORT も export する。ここで解決した値をヘルスチェック（HEALTH_URL）と
# compose の公開ポートで必ず一致させるため（`.env` に WEB_HOST_PORT の行が無い環境で、
# compose 側の既定値 8080 だけが効いて両者がずれるのを防ぐ）。
export WEB_HOST_PORT

COMPOSE="docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE"

MODE="${1:-}"

case "$MODE" in
  app|migrate|reset) ;;
  *)
    err "Mode required. Usage: $0 <app|migrate|reset>"
    exit 1
    ;;
esac

# ===== エラー時診断: 失敗したモジュールのログを出して終了する =====
ALL_SERVICES=(init-paths db web nginx)

# このデプロイが作るコンテナ名。compose の既定（`<プロジェクト>-<サービス>-1`）と
# docker-compose.yml で `container_name` を指定している db だけ別扱いにする。
expected_container_names() {
  local svc
  for svc in "${ALL_SERVICES[@]}"; do
    case "$svc" in
      db) echo "$DB_CONTAINER_NAME" ;;
      *)  echo "${PROJECT}-${svc}-1" ;;
    esac
  done
}

# `$COMPOSE ps` はこのプロジェクトのラベルを持つコンテナしか映さない。名前だけを
# 握っている残骸は映らないので、名前で引いた実体も併せて出す。
dump_container_name_holders() {
  local name holders found=0
  echo "$TAG ---- containers holding this project's names ----" >&2
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    # 先頭の `/` の有無は Docker のバージョンで変わるため `^/?` で両方に当てる
    # （`^/name$` だけだと新しい Docker で 1 件も引けず、診断が空になる）。
    holders="$(docker ps -a --filter "name=^/?${name}$" \
      --format '{{.ID}}  {{.Names}}  {{.State}}  project={{.Label "com.docker.compose.project"}}' 2>/dev/null || true)"
    [ -n "$holders" ] || continue
    found=1
    echo "$holders" >&2
  done < <(expected_container_names)
  # 「1 件も無い」こと自体が手掛かりになる（名前だけ握られている状態）ので明示する。
  [ "$found" = 1 ] || echo "  (none — 名前を握っているコンテナの実体は無い)" >&2
}

dump_module_logs() { # 引数: サービス名...
  echo "" >&2
  echo "----- diagnostics ($TAG) -----" >&2
  $COMPOSE ps -a >&2 || true
  dump_container_name_holders
  local svc
  for svc in "$@"; do
    echo "" >&2
    echo "$TAG ---- module logs: $svc (last 100 lines) ----" >&2
    $COMPOSE logs --tail 100 --timestamps "$svc" >&2 || true
  done
  echo "------------------------------" >&2
}

fail() { # 引数: メッセージ [ログを出すサービス名...]
  local msg="$1"
  shift || true
  err "$msg"
  if [ $# -gt 0 ]; then
    dump_module_logs "$@"
  fi
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
}

on_unexpected_error() {
  local line="$1"
  err "Unexpected error at line $line (mode: $MODE)"
  dump_module_logs "${ALL_SERVICES[@]}"
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
}
trap 'on_unexpected_error $LINENO' ERR

log "${APP_NAME} deploy start (env: $ENV_NAME, mode: $MODE, base: $BASE_DIR)"

# ===== Preflight: docker daemon must be reachable =====
if ! docker info >/dev/null 2>&1; then
  err "Cannot reach the Docker daemon (permission denied or daemon down)."
  echo "  Run this script with sudo, or add your user to the 'docker' group and re-login." >&2
  exit 1
fi

log "Mount root: $HOST_DATA_ROOT"
log "Web host port: $WEB_HOST_PORT (source: $WEB_HOST_PORT_SOURCE)"

load_image() {
  local tar="$1"
  log "Loading image: $tar ($(du -h "$tar" 2>/dev/null | cut -f1))"
  docker load -i "$tar"
}

retag_for_env() { # 引数: <ロード時タグ> <環境別タグ>
  local loaded="$1" target="$2"
  docker tag "$loaded" "$target" || fail "Failed to tag $loaded as $target"
  log "Tagged $loaded -> $target"
}

# ===== Load app image =====
if [ -n "$MANIFEST_COMMIT" ]; then
  log "Manifest: commit=$MANIFEST_COMMIT version=${version:-unknown} build=${build_date:-unknown}"
fi
if [ -f "$IMAGE_TAR" ]; then
  verify_tar_checksum "$(basename "$IMAGE_TAR")" \
    || fail "image.tar が manifest.sha256 と一致しません（転送破損の可能性。dist/ を配置し直してください）"
  if image_matches_manifest "$LOADED_APP_REF" "$MANIFEST_APP_IMAGE_ID"; then
    log "App image already loaded ($LOADED_APP_REF matches manifest); skipping docker load"
  else
    load_image "$IMAGE_TAR"
  fi
  retag_for_env "$LOADED_APP_REF" "$APP_IMAGE"
elif docker image inspect "$APP_IMAGE" >/dev/null 2>&1; then
  warn "Image tar not found: $IMAGE_TAR — reusing already-loaded $APP_IMAGE"
else
  err "Image tar not found: $IMAGE_TAR"
  echo "  ビルドマシンで './scripts/build.sh' を実行し、dist/ の中身を配置してください。" >&2
  exit 1
fi

# ===== Sync deploy assets from the loaded image =====
# 配置先の compose / nginx 設定が古いまま残る事故を防ぐため、イメージに焼き込まれた
# コピーをロード直後に取り出し、常にイメージと同じ版を使う。環境ごとの違いは
# すべて .env 側で表現する。
sync_assets_from_image() {
  local cid
  if ! cid=$(docker create "$APP_IMAGE" 2>/dev/null); then
    warn "Could not inspect $APP_IMAGE; skipping asset sync"
    return 0
  fi

  if docker cp "$cid:/app/docker-compose.yml" "$COMPOSE_FILE.new" >/dev/null 2>&1; then
    mv -f "$COMPOSE_FILE.new" "$COMPOSE_FILE"
    log "compose file synced from image -> $COMPOSE_FILE"
  else
    rm -f "$COMPOSE_FILE.new"
    warn "$APP_IMAGE has no /app/docker-compose.yml; keeping existing file if any"
  fi

  local nginx_conf_dst="$BASE_DIR/docker/nginx/default.conf"
  mkdir -p "$(dirname "$nginx_conf_dst")"
  if docker cp "$cid:/app/docker/nginx/default.conf" "$nginx_conf_dst.new" >/dev/null 2>&1; then
    mv -f "$nginx_conf_dst.new" "$nginx_conf_dst"
    log "nginx config synced from image -> $nginx_conf_dst"
  else
    rm -f "$nginx_conf_dst.new"
    warn "$APP_IMAGE has no nginx config; keeping existing file if any"
  fi

  docker rm -f "$cid" >/dev/null 2>&1 || true
}
sync_assets_from_image

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "No docker-compose.yml found at $COMPOSE_FILE (image sync also failed)"
fi

# ===== Ensure .env exists (zero-config deploy) =====
# 値はすべて docker-compose.yml 側の ${VAR:-default} が供給するので、生成する
# .env は上書き用のコメント付きテンプレートで足りる。既存の .env には触れない。
# WEB_HOST_PORT は上で解決した値（`.env` 未生成なので既定値、または引き継がれた
# APP_WEB_HOST_PORT）が書き込まれる。以後この `.env` が正本になる（ADR-0008）。
if [ ! -f "$ENV_FILE" ]; then
  warn "$ENV_FILE not found; generating a default template."
  cat > "$ENV_FILE" <<ENVEOF
# 自動生成された .env（deploy スクリプトが作成。環境: $ENV_NAME）。
# 既定の資格情報は開発向け。外部公開する場合は必ず上書きして再デプロイする。
# すべての項目は .env.example を参照。

# --- 環境固有の実値（この環境ディレクトリに閉じた値に固定する）---
# DB はホストへポートを公開しない（ADR-0013）。stg / prod を同一ホストで動かしても
# 衝突しないのはコンテナ名とネットワーク名を環境ごとに分けているため。
HOST_DATA_ROOT=$BASE_DIR/mnt
WEB_HOST_PORT=$WEB_HOST_PORT
DB_CONTAINER_NAME=$DEFAULT_DB_CONTAINER
DOCKER_NETWORK_NAME=$DEFAULT_NETWORK

# --- 上書き推奨（未設定なら開発向け既定値で動作する）---
# MARIADB_ROOT_PASSWORD=strong-mariadb-root-password-here
# MARIADB_USER=web_user
# MARIADB_PASSWORD=strong-mariadb-password-here
# MARIADB_DATABASE=appdb
# JWT_SECRET_KEY=strong-random-secret-here
# SECRET_KEY=strong-random-secret-here
# APP_BASE_URL=https://app.example.com
# ADMIN_INITIAL_PASSWORD=change-me-strong
ENVEOF
fi

# DB コンテナ名を compose と同じ規則で解き直す（`.env` の値 ＞ docker-compose.yml の
# `${DB_CONTAINER_NAME:-fastapitemplate-mariadb}`）。名前の衝突を調べるとき、compose が
# 実際に使う名前と一致していないと見落とすため、環境ごとの既定値では代用しない。
DB_CONTAINER_NAME="$(env_file_value DB_CONTAINER_NAME)"
DB_CONTAINER_NAME="${DB_CONTAINER_NAME:-${APP_NAME}-mariadb}"

# ===== Ensure DB image is available under the env-specific tag =====
ensure_db_image() {
  if docker image inspect "$DB_IMAGE" >/dev/null 2>&1; then
    return 0
  fi
  if [ -f "$IMAGE_DB_TAR" ]; then
    verify_tar_checksum "$(basename "$IMAGE_DB_TAR")" \
      || fail "image-db.tar が manifest.sha256 と一致しません（転送破損の可能性。dist/ を配置し直してください）"
    load_image "$IMAGE_DB_TAR"
    retag_for_env "$LOADED_DB_REF" "$DB_IMAGE"
    return 0
  fi
  if docker image inspect "$LOADED_DB_REF" >/dev/null 2>&1; then
    retag_for_env "$LOADED_DB_REF" "$DB_IMAGE"
    return 0
  fi
  fail "DB image not found: $DB_IMAGE（'./scripts/build.sh' で dist/image-db.tar を作成し配置してください）"
}

# ===== Stop running containers =====
# --remove-orphans を付けるのは、過去の compose ファイルにしか無いサービス
# （リネーム・削除されたもの）のコンテナがプロジェクトに残り、次の up で名前を
# 取り合うのを防ぐため。
log "docker compose down"
$COMPOSE down --remove-orphans || true

# ===== コンテナ名の衝突を解消する =====
# `docker compose down` が消すのは「このプロジェクトのラベルを持つコンテナ」だけで、
# 同じ名前を握った残骸までは面倒を見ない。残骸が残る経路は主に 2 つある。
#   1. compose 管理外で作られた（ラベルが無い）コンテナ
#   2. 削除処理が途中で止まり、実体は無いのに名前だけ Docker が掴んでいる
# どちらも `docker compose ps` には映らないまま、次の up が
# `Conflict. The container name "/…" is already in use` で落ちる。
#
# 消してよいかはラベル `com.docker.compose.project` だけで判定する:
#   このプロジェクト / ラベル無し / inspect もできない → 残骸なので消す
#   別プロジェクト → stg など別環境が稼働中かもしれないので、消さずに中断する
#
# 掃除の結果は 3 通りある。呼び出し側は終了コードで区別する:
#   0 … 名前を空けた（実体のあるコンテナを消した）
#   1 … 別プロジェクトが持ち主。運用者が `.env` を直すまで解消しない
#   2 … 実体が無いまま Docker が名前を握っている。デーモンの再起動が要る
container_project_label() { # 引数: <コンテナ名または ID>
  docker inspect -f '{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.project"}}{{end}}' "$1" 2>/dev/null
}

# 実体の無い名前を握られている状態の診断。ここまで来るとスクリプトでは解消できない。
# デーモンの再起動はホスト全体に影響するため、デプロイスクリプトからは行わない（ADR-0014）。
report_phantom_name_holder() { # 引数: <コンテナ ID または名前>
  err "Docker still holds the container name, but no container is behind it: $1"
  echo "  実体が無いまま名前だけ掴まれているため、削除でも解消しません" >&2
  echo "  （docker ps -a にも docker inspect にも出ません）。" >&2
  echo "  Docker デーモンを再起動してから、もう一度デプロイしてください:" >&2
  echo "    sudo systemctl restart docker" >&2
  echo "    # Synology DSM: Container Manager を停止 → 起動" >&2
}

remove_leftover_container() { # 引数: <コンテナ名または ID>
  local ref="$1" project rm_output
  project="$(container_project_label "$ref" || true)"
  if [ -n "$project" ] && [ "$project" != "$PROJECT" ]; then
    err "Container '$ref' belongs to another compose project ('$project') and holds a name this deploy needs."
    echo "  別環境が稼働中の可能性があるため自動では消しません。コンテナ名の重複" >&2
    echo "  （各環境の .env の DB_CONTAINER_NAME・環境ディレクトリ名）を見直してください。" >&2
    return 1
  fi
  warn "Removing leftover container holding a name this deploy needs: $ref"
  # `docker rm -f` は「そもそもコンテナが無い」ときも成功（終了コード 0）で返す。
  # 実体が無いまま名前だけ握られている残骸はまさにこれに当たるので、終了コードを
  # 信じると「消せた」と誤認し、同じ相手との衝突でもう一度落ちる。出力で見分ける。
  if ! rm_output="$(docker rm -f "$ref" 2>&1)"; then
    err "Could not remove the leftover container: $ref"
    if [ -n "$rm_output" ]; then
      echo "  $rm_output" >&2
    fi
    report_phantom_name_holder "$ref"
    return 2
  fi
  if echo "$rm_output" | grep -qi 'no such container'; then
    report_phantom_name_holder "$ref"
    return 2
  fi
  return 0
}

# up の前に、このデプロイが作る名前を先回りして空ける。
clear_leftover_containers() {
  local name found=0 status
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    docker container inspect "$name" >/dev/null 2>&1 || continue
    found=1
    remove_leftover_container "$name" && status=0 || status=$?
    [ "$status" = 0 ] || return "$status"
  done < <(expected_container_names)
  [ "$found" = 0 ] || log "Cleared leftover containers before starting"
  return 0
}

# 名前だけ掴まれている残骸は inspect でも ps でも見えない。up の失敗メッセージには
# 衝突相手のコンテナ ID が入るので、そこから拾って消す。
conflicting_container_ids() { # 引数: <up の出力ファイル>
  sed -n 's/.*already in use by container "\([0-9a-f]\{6,\}\)".*/\1/p' "$1" | sort -u
}

# 終了コードは remove_leftover_container と同じ（0 / 1 / 2）。
# ただし「そもそも名前衝突ではない」場合も 1 を返す（診断はいつもどおり出す）。
clear_conflicts_from_output() { # 引数: <up の出力ファイル>
  local ids id status
  ids="$(conflicting_container_ids "$1")"
  [ -n "$ids" ] || return 1
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    remove_leftover_container "$id" && status=0 || status=$?
    [ "$status" = 0 ] || return "$status"
  done <<< "$ids"
  return 0
}

# ===== Reset mode: clear data =====
if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all $ENV_NAME DB & app data.\033[0m"
  if [ -f "$IMAGE_DB_TAR" ]; then
    verify_tar_checksum "$(basename "$IMAGE_DB_TAR")" \
      || fail "image-db.tar が manifest.sha256 と一致しません（転送破損の可能性。dist/ を配置し直してください）"
    load_image "$IMAGE_DB_TAR"
    retag_for_env "$LOADED_DB_REF" "$DB_IMAGE"
  else
    warn "[reset] DB image tar not found: $IMAGE_DB_TAR"
  fi
  echo "[reset] Deleting $DB_PATH and $DATA_PATH"
  rm -rf "$DB_PATH" "$DATA_PATH"
fi

ensure_db_image

# ===== Ensure the host mount root exists =====
# バインドマウント元が無いとコンテナが一切起動しない（ログも残らない）ため、
# マウントルートだけはここで確実に作る。サブディレクトリは init-paths が作る。
log "Ensuring host mount root exists: $HOST_DATA_ROOT"
mkdir -p "$HOST_DATA_ROOT" || fail "Could not create host mount root: $HOST_DATA_ROOT"

clear_leftover_containers || fail "Could not free the container names this deploy needs"

# ===== Start containers =====
UP_OUTPUT="$(mktemp)"
trap 'rm -f "$UP_OUTPUT"' EXIT

# 出力は失敗時に衝突相手の ID を取り出すので、tee で見せつつファイルにも残す。
compose_up() { $COMPOSE up -d --remove-orphans 2>&1 | tee "$UP_OUTPUT"; }

log "docker compose up -d"
if ! compose_up; then
  # 名前衝突なら相手を消して 1 度だけやり直す。それ以外の失敗はそのまま診断へ回す。
  first_conflicts="$(conflicting_container_ids "$UP_OUTPUT")"
  clear_conflicts_from_output "$UP_OUTPUT" && clear_status=0 || clear_status=$?
  # 実体の無い名前を握られている場合（2）は、コンテナが 1 つも無いのでモジュール
  # ログを出しても空になる。診断は report_phantom_name_holder が出し切っている。
  if [ "$clear_status" = 2 ]; then
    fail "Could not free the container names this deploy needs"
  fi
  if [ "$clear_status" != 0 ]; then
    fail "docker compose up failed" "${ALL_SERVICES[@]}"
  fi

  log "Retrying docker compose up after clearing the conflicting container(s)"
  if ! compose_up; then
    # 同じ相手ともう一度衝突したなら、消したつもりの名前が解放されていない。
    # `docker rm -f` が成功を返しても名前が空いていないケースがここに落ちる。
    retry_conflicts="$(conflicting_container_ids "$UP_OUTPUT")"
    if [ -n "$retry_conflicts" ] && [ "$retry_conflicts" = "$first_conflicts" ]; then
      report_phantom_name_holder "$retry_conflicts"
      fail "Could not free the container names this deploy needs"
    fi
    fail "docker compose up failed" "${ALL_SERVICES[@]}"
  fi
fi

# ===== Schema sync =====
run_migrations_with_retry() {
  local attempt
  for attempt in 1 2 3; do
    if $COMPOSE exec -T web python scripts/run_db_migrations.py; then
      return 0
    fi
    warn "DB migration failed (attempt $attempt/3); retrying in 5s"
    sleep 5
  done
  fail "DB migration failed after 3 attempts" web db
}

case "$MODE" in
  migrate|reset)
    # migrate: 既存データを保持したまま新しい migration だけを適用する。
    # reset: 空 DB にスキーマ + マスタデータを構築する（entrypoint も冪等に流すが
    # ここでも確実に head まで揃える）。
    log "Applying DB migrations"
    run_migrations_with_retry
    ;;
esac

# ===== Wait for health check =====
log "Waiting for service health: $HEALTH_URL"
for i in $(seq 1 60); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    log "Service healthy"
    break
  fi
  log "...waiting ($i/60)"
  sleep 2
done

if ! curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
  err "Health check failed: $HEALTH_URL"
  dump_module_logs web nginx
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
fi

# ===== Cleanup old images =====
log "Cleaning old unused Docker images"
docker image prune -f > /dev/null 2>&1 || true

# ===== Show deployed version =====
log "Deployed version:"
$COMPOSE exec -T web cat /app/shared/kernel/version.json 2>/dev/null || warn "Could not read version.json"

echo -e "\033[32m${TAG} Deploy complete (mode: $MODE)\033[0m"
