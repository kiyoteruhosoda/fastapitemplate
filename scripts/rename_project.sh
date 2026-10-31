#!/usr/bin/env bash
# 雛形の名前を、派生アプリの名前へ付け替える（ADR-0099）。
#
#   scripts/rename_project.sh <new-name>
#
# 追跡しているファイルの中の名前を全部置き換える。コミットはしない（git diff で見てからコミットする）。
# ⚠ docs/CHANGELOG.md と docs/decisions/ は書き換えない（雛形の履歴と決定の記録だから）。
# ⚠ このファイルに名前をそのまま書かない。[t] を挟むと、自分自身も確かめの git grep も引っかからない。
set -euo pipefail

readonly OLD_NAME_PATTERN='fastapi[t]emplate'
readonly TEMPLATE_REMOTE_URL='https://git.nolumia.com/kyon/fastapi''template.git'
readonly KEPT_AS_RECORDS=(':!docs/CHANGELOG.md' ':!docs/decisions')

new_name="${1:-}"

# namespace（<app>-<env> で 63 文字まで）・イメージ名・pyproject の name のすべてに使える形だけを通す
if [[ ! "$new_name" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || ((${#new_name} > 40)); then
    echo "使い方: scripts/rename_project.sh <new-name>" >&2
    echo "名前は小文字の英字で始め、小文字の英数字とハイフンだけで、40 文字まで（例: my-app）。" >&2
    exit 2
fi
if [[ "$new_name" =~ ^$OLD_NAME_PATTERN$ ]]; then
    echo "雛形と同じ名前には付け替えられません。" >&2
    exit 2
fi

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "コミットしていない変更があります。戻せるように、先にコミットしてください。" >&2
    exit 1
fi

mapfile -t files < <(git grep -I -l -i -E "$OLD_NAME_PATTERN" -- "${KEPT_AS_RECORDS[@]}" || true)
if ((${#files[@]} == 0)); then
    echo "雛形の名前はもう残っていません（付け替え済みです）。" >&2
    exit 1
fi

sed -i -E "s/$OLD_NAME_PATTERN/$new_name/Ig" "${files[@]}"

# 雛形の更新を取り込む先（docs/TEMPLATE.md 5 章）。付け替えると文書から URL が消えるので、ここで足す
if ! git remote get-url template >/dev/null 2>&1; then
    git remote add template "$TEMPLATE_REMOTE_URL"
fi

echo "${#files[@]} 個のファイルを ${new_name} へ付け替えました。git diff で見てからコミットしてください。"
