#!/usr/bin/env bash
# scripts/build-remote-container.sh — git 非搭載のデプロイ先（例: Synology DSM）向けの一ホスト方式。
#
# ソース取得＆イメージビルドは「dev コンテナ」内で行い（コンテナに git・ツールチェーンがある前提）、
# 生成された dist/ をコンテナのワークスペース（ホストから見えるパス）からデプロイ先へ取り込み、
# 同梱の deploy.sh を実行する。**デプロイ先に git は不要**。
#
# 4 ステップを 1 本で実行する:
#   SYNC   … dev コンテナ内で git pull（最新ソース取得）
#   BUILD  … dev コンテナ内で scripts/build.sh（dist/ を生成）
#   PICK   … ビルド済み dist/ をデプロイ先へ取り込み
#   DEPLOY … 取り込んだ deploy.sh を実行
#
# 自己更新（self-update）: このスクリプト自身は dist/ に含まれない手置きブートストラップのため、
# git pull では更新されない。そこで SYNC 後に dev コンテナ内の最新 build-remote-container.sh と
# byte 比較し、異なれば最新版へ自分自身を差し替えて同じ引数で自動再実行する（初回に限らず毎回）。
# ※ この自動更新が働くのは「本スクリプトが既に self-update 対応版であること」が前提。まだ未対応の
#   古い版がデプロイ先にある場合は、一度だけ手動で最新版へ差し替える必要がある（以後は自動）。
#
# 使い方（デプロイ先で。モードはどの引数位置でも拾う。既定 app）:
#   ./build-remote-container.sh            # app（通常デプロイ）
#   ./build-remote-container.sh migrate
#   ./build-remote-container.sh reset
#
# 設定は環境変数、または下記 `build-remote-container.env` で行う。
# **スクリプト冒頭の既定値を直接書き換えてはならない**（self-update が本ファイルを最新版で丸ごと
# 差し替えるため、直接編集した値は次回実行時に失われる。設定は必ず env ファイル／環境変数で与える）:
#   APP_PROJECT        プロジェクト名（省略時はデプロイ先ディレクトリの親から自動取得。下記）
#   APP_DEV_CONTAINER  ビルドを行う dev コンテナ名
#   APP_DEV_USER       コンテナ内でビルドする実行ユーザー
#   APP_DEV_WORKDIR    コンテナ内のリポジトリ working dir（scripts/build.sh がある場所）
#   APP_DIST_DIR       ホストから見えるビルド済み dist/ の絶対パス（必須。無指定はエラー）
#   APP_TARGET_DIR     デプロイ先ディレクトリ（既定: このスクリプトの場所）
#
# ディレクトリ構成の前提は **/<プロジェクト名>/<環境>**（例: /volume1/docker/fastapitemplate/prod）。
#   * 環境（stg/prod 等）  … デプロイ先ディレクトリ名から取得
#   * プロジェクト名        … デプロイ先ディレクトリの親ディレクトリ名から取得
# プロジェクト名の優先順位: APP_PROJECT > 設定ファイル PROJECT > 親ディレクトリ名 > 既定値 fastapitemplate。
# この構成に従っていれば PROJECT の指定は不要。従わない場合は APP_PROJECT／PROJECT で明示する。
#
# 設定は上記の環境変数のほか、**スクリプトと同じ場所の `build-remote-container.env`**（KEY=VALUE 形式）
# にも書ける（`export` 等のコマンド実行は不要）。各パスの `{PROJECT}` は確定した project 値へ展開される。例:
#     APP_DEV_CONTAINER=ubuntu-dev
#     APP_DEV_WORKDIR=/work/project/{PROJECT}
#     APP_DIST_DIR=/volume1/homes/user/work/project/{PROJECT}/dist
# ※ デプロイ用 `.env`（deploy.sh / Compose が読む秘密情報ファイル）とは別物。ここへ書いても効かない。
#
# 前提: docker（デプロイ先）と、ビルド用 dev コンテナが起動していること。
set -euo pipefail

# ---- 設定ファイル（任意）を読み込む: <スクリプトと同じ場所>/build-remote-container.env -----
# KEY=VALUE 行だけを安全に取り込む（source/eval しない）。既に設定済みの環境変数を優先し、
# 未設定のものだけ設定ファイルの値で補う。行頭コメント（#）・空行・不正キーは無視し、値は前後空白と
# 空白に続くインラインコメント（` # ...`）を除去する（`#` を含む値でも空白が前に無ければ保持）。
_config_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build-remote-container.env"
_config_loaded_keys=()   # 設定ファイルから実際に取り込んだキー（起動情報の表示用）
if [[ -f "$_config_file" ]]; then
  while IFS= read -r _line || [[ -n "$_line" ]]; do
    _line="${_line%$'\r'}"
    [[ "$_line" =~ ^[[:space:]]*# ]] && continue
    [[ "$_line" == *=* ]] || continue
    _key="${_line%%=*}"
    _val="${_line#*=}"
    _key="${_key//[[:space:]]/}"
    _val="${_val%%[[:space:]]#*}"                 # 空白+# 以降のインラインコメントを除去
    _val="${_val#"${_val%%[![:space:]]*}"}"       # 先頭空白を除去
    _val="${_val%"${_val##*[![:space:]]}"}"       # 末尾空白を除去
    [[ "$_key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ -z "${!_key:-}" ]]; then
      export "$_key=$_val"
      _config_loaded_keys+=("$_key")
    fi
  done <"$_config_file"
fi

log() { printf '[fastapitemplate:container] %s\n' "$*" >&2; }
die() { printf '[fastapitemplate:container][error] %s\n' "$*" >&2; exit 1; }

# ---- ターゲットディレクトリ・自分自身のパスを先に確定する ---------------------------
# 想定ディレクトリ構成は /<プロジェクト名>/<環境>（例: /volume1/docker/fastapitemplate/prod）。
# 環境はターゲットディレクトリ名、プロジェクト名はその親ディレクトリ名から取得する（下記）。
target_dir="${APP_TARGET_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
# 相対・非正規化パス（例 APP_TARGET_DIR=stg や 末尾 /.）でも親ディレクトリを正しく導出できるよう、
# 絶対・正規化済みパスへ解決してから親を取る（cd が . / .. を畳む）。存在しなければ明示エラー。
target_dir="$(cd "$target_dir" 2>/dev/null && pwd)" \
  || die "APP_TARGET_DIR のディレクトリが存在しません: ${APP_TARGET_DIR:-（スクリプトの場所）}"
# self-update で自分自身を差し替えるため、絶対パスをここ（cd の前）で 1 度だけ確定する。
# cd "$target_dir" 後に相対 BASH_SOURCE[0] を再解決すると別ディレクトリを指してしまう
# （例: ./stg/build-remote-container.sh 起動で target_dir へ cd 済みだと ./stg が二重展開される）。
self_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

# ---- 既定値（設定ファイル build-remote-container.env／環境変数で上書きする） ---------
# ここの既定値は直接書き換えないこと（self-update が本ファイルを差し替えるため編集は失われる。
# 環境固有の設定は build-remote-container.env か環境変数で与える）。
# プロジェクト名は 1 度だけ確定する。優先順位: 環境変数 APP_PROJECT > 設定ファイル PROJECT >
# ターゲットディレクトリの親ディレクトリ名（/<プロジェクト名>/<環境> 前提）> 既定値 fastapitemplate。
_project_from_dir="$(basename "$(dirname "$target_dir")")"
case "$_project_from_dir" in '' | '/' | '.' | '..') _project_from_dir='' ;; esac
project="${APP_PROJECT:-${PROJECT:-${_project_from_dir:-fastapitemplate}}}"
# プロジェクト名の出所（起動ログで「なぜこの値か」を分かるように表示する）。
if   [[ -n "${APP_PROJECT:-}" ]]; then project_source="環境変数 APP_PROJECT"
elif [[ -n "${PROJECT:-}"     ]]; then project_source="設定ファイル PROJECT"
elif [[ -n "$_project_from_dir" ]]; then project_source="ディレクトリ（$target_dir の親）"
else                                    project_source="既定値"
fi
dev_container="${APP_DEV_CONTAINER:-ubuntu-dev}"
dev_user="${APP_DEV_USER:-sshuser}"
dev_workdir="${APP_DEV_WORKDIR:-/work/project/$project}"
dist_dir="${APP_DIST_DIR:-}"

# パス中の {PROJECT} を project の値へ展開する（プロジェクト名の一元管理）。
# 置換文字列側では bash 5.2 の patsub_replacement により `&`（マッチ全体）・`\` が
# 特別扱いされるため、project 値を差し込む前に両者をエスケープしてリテラル挿入する。
_project_repl="${project//\\/\\\\}"
_project_repl="${_project_repl//&/\\&}"
dev_workdir="${dev_workdir//\{PROJECT\}/$_project_repl}"
dist_dir="${dist_dir//\{PROJECT\}/$_project_repl}"

# モードは引数のどこにあっても拾う（余分な語が前に付いても動く）。既定 app。
mode=app
for arg in "$@"; do
  case "$arg" in app | migrate | reset) mode="$arg" ;; esac
done

# 表示用の環境ラベル（デプロイ先ディレクトリ名）。deploy.sh も同じ名前から stg / prod を判定する。
environment="$(basename "$target_dir")"

# ---- 起動情報（どの環境へ・どのモードで動き・どの設定を読み込み・どう解決したかを表示） ----
log "══════════════════════════════════════════════"
log "  環境 (ENV) : $environment"
log "  モード     : $mode"
log "  project    : $project"
log "══════════════════════════════════════════════"
log "  引数        : $([[ $# -gt 0 ]] && printf '%q ' "$@" || printf '(なし → 既定 %s)' "$mode")"
if [[ -f "$_config_file" ]]; then
  if [[ ${#_config_loaded_keys[@]} -gt 0 ]]; then
    log "  設定ファイル: $_config_file （読込: ${_config_loaded_keys[*]}）"
  else
    log "  設定ファイル: $_config_file （取り込んだキーなし＝全て環境変数が優先）"
  fi
else
  log "  設定ファイル: なし（$_config_file 不在。環境変数と既定値のみ）"
fi
log "  解決した設定:"
log "    PROJECT           = $project （出所: $project_source）"
log "    APP_DEV_CONTAINER = $dev_container"
log "    APP_DEV_USER      = $dev_user"
log "    APP_DEV_WORKDIR   = $dev_workdir"
log "    APP_DIST_DIR      = ${dist_dir:-(未設定)}"
log "    APP_TARGET_DIR    = $target_dir （環境=$environment）"

command -v docker >/dev/null 2>&1 || die "docker が見つかりません。"
[[ -n "$dist_dir" ]] || die "APP_DIST_DIR（ホストから見えるビルド済み dist/ の絶対パス）を設定してください。"

cd "$target_dir"

# --- SYNC（dev コンテナ内で git pull だけ先に行う。build.sh はまだ走らせない） -------
# self-update（下記）より前に最新ソースを取得しておくことで、この後で最新の
# build-remote-container.sh を dev コンテナから取り出して自分自身と比較できるようにする。
log "SYNC   dev コンテナ '$dev_container' で git pull します（$dev_workdir）..."
docker exec -u "$dev_user" "$dev_container" bash -lc "
  set -e
  cd '$dev_workdir'
  git pull --ff-only
" || die "dev コンテナ内での git pull に失敗しました。"

# --- SELF-UPDATE（このスクリプト自身が古ければ最新版へ差し替えて再実行。初回に限らず毎回） ---
# デプロイ先の build-remote-container.sh は dist/ に含まれない「手置きブートストラップ」なので
# git pull しても自動更新されない。ここで dev コンテナ内の最新版と byte 単位で比較し、異なれば
# 最新版で自分自身を置き換えて同じ引数で再実行する。APP_SELF_UPDATED で再実行は 1 回に限定し
# 無限ループを防ぐ（再実行後の git pull は no-op・self-update はスキップし、そのまま BUILD へ進む）。
if [[ "${APP_SELF_UPDATED:-0}" != "1" ]]; then
  if _self_tmp="$(mktemp "$(dirname "$self_path")/.build-remote-container.XXXXXX" 2>/dev/null)"; then
    if docker exec -u "$dev_user" "$dev_container" \
          bash -lc "cat '$dev_workdir/scripts/build-remote-container.sh'" >"$_self_tmp" 2>/dev/null \
        && [[ -s "$_self_tmp" ]] && ! cmp -s "$_self_tmp" "$self_path"; then
      log "SELF-UPDATE  build-remote-container.sh が更新されています。最新版へ差し替えて再実行します。"
      # mktemp は 0600 で作るため、差し替え後に他ユーザー・別の自動化アカウントから実行できなくなる。
      # 既存スクリプトのパーミッションを引き継ぐ（取得できなければ実行に必要な 0755 を明示付与する）。
      chmod --reference="$self_path" "$_self_tmp" 2>/dev/null \
        || chmod "$(stat -c '%a' "$self_path" 2>/dev/null || echo 755)" "$_self_tmp" 2>/dev/null \
        || chmod 0755 "$_self_tmp"
      # 同一ディレクトリ内 rename でアトミックに差し替える（実行中プロセスの fd は旧 inode を保持し、
      # 直後の exec がパス経由で新 inode を開き直すため、実行中スクリプトの破損を避けられる）。
      mv -f "$_self_tmp" "$self_path"
      export APP_SELF_UPDATED=1
      exec "$self_path" "$@"
    fi
    rm -f "$_self_tmp"
  else
    log "SELF-UPDATE  一時ファイルを作成できないためスキップします（$self_path のディレクトリ書込権限を確認）。"
  fi
fi

# --- BUILD（dev コンテナ内で build.sh。git pull は SYNC 済み） ---------------------
log "BUILD  dev コンテナ '$dev_container' でビルドします（$dev_workdir）..."
docker exec -u "$dev_user" "$dev_container" bash -lc "
  set -e
  cd '$dev_workdir'
  ./scripts/build.sh
" || die "コンテナ内ビルドに失敗しました。"

# --- PICK（ビルド済み dist をデプロイ先へ取り込み） --------------------------------
log "PICK   $dist_dir → $target_dir"
[[ -d "$dist_dir" ]] || die "dist が見つかりません: $dist_dir（build.sh の出力先か APP_DIST_DIR を確認）。"
# デプロイ先の .env は取り込みで絶対に壊さない（秘密情報を保全）。万一 dist 側に .env が紛れても
# 上書きしないよう、コピー前に退避し、コピー後に戻す（.env の管理は deploy.sh に一本化）。
env_backup=""
if [[ -f "$target_dir/.env" ]]; then
  env_backup="$(mktemp)"
  cp -a "$target_dir/.env" "$env_backup"
fi
cp -a "$dist_dir/." "$target_dir/"
if [[ -n "$env_backup" ]]; then
  mv -f "$env_backup" "$target_dir/.env"
fi
[[ -f "$target_dir/deploy.sh" ]] || die "deploy.sh が取り込まれていません（build.sh の出力を確認）。"
chmod +x "$target_dir"/*.sh 2>/dev/null || true

# --- DEPLOY（.env は deploy.sh が管理: 初回生成・以後は不変） ----------------------
log "DEPLOY ./deploy.sh $mode"
"$target_dir/deploy.sh" "$mode"

log "END    環境=$environment  モード=$mode（完了）"
