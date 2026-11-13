#!/usr/bin/env bash
# Rename the template's name to the derived app's name (ADR-0099).
#
#   scripts/rename_project.sh <new-name>
#
# Replaces every occurrence of the name in tracked files. Does not commit (review with git diff, then commit).
# ⚠ docs/CHANGELOG.md and docs/decisions/ are not rewritten (they record the template's history and decisions).
# ⚠ Never write the name literally in this file. With [t] inserted, neither this file nor the
#   verifying git grep matches it.
set -euo pipefail

readonly OLD_NAME_PATTERN='fastapi[t]emplate'
readonly TEMPLATE_REMOTE_URL='https://git.nolumia.com/kyon/fastapi''template.git'
readonly KEPT_AS_RECORDS=(':!docs/CHANGELOG.md' ':!docs/decisions')

new_name="${1:-}"

# Accept only names valid for all of: namespace (<app>-<env>, up to 63 chars), image name, pyproject name
if [[ ! "$new_name" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || ((${#new_name} > 40)); then
    echo "Usage: scripts/rename_project.sh <new-name>" >&2
    echo "The name must start with a lowercase letter, use only lowercase letters, digits and hyphens, and be at most 40 characters (e.g. my-app)." >&2
    exit 2
fi
if [[ "$new_name" =~ ^$OLD_NAME_PATTERN$ ]]; then
    echo "Cannot rename to the same name as the template." >&2
    exit 2
fi

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "There are uncommitted changes. Commit them first so the rename can be undone." >&2
    exit 1
fi

mapfile -t files < <(git grep -I -l -i -E "$OLD_NAME_PATTERN" -- "${KEPT_AS_RECORDS[@]}" || true)
if ((${#files[@]} == 0)); then
    echo "The template name no longer appears anywhere (already renamed)." >&2
    exit 1
fi

sed -i -E "s/$OLD_NAME_PATTERN/$new_name/Ig" "${files[@]}"

# Remote for pulling template updates (docs/TEMPLATE.md chapter 5). Renaming removes the URL from
# the docs, so add it here
if ! git remote get-url template >/dev/null 2>&1; then
    git remote add template "$TEMPLATE_REMOTE_URL"
fi

echo "Renamed ${#files[@]} file(s) to ${new_name}. Review with git diff, then commit."
