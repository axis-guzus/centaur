#!/bin/bash
# Clone recently-active repositories from specified GitHub orgs.
# Requires: gh CLI authenticated (`gh auth status`)
#
# Usage:
#   ./clone-repos.sh              # Clone repos pushed in last 30 days
#   ./clone-repos.sh paradigmxyz  # Clone only one org
#
# Environment:
#   MAX_JOBS=16    — parallel clone workers (default: 16)
#   SINCE_DAYS=30  — only repos pushed within this many days (default: 30)
set -euo pipefail

REPOS_DIR="$(cd "$(dirname "$0")" && pwd)/repos"
MAX_JOBS="${MAX_JOBS:-16}"
SINCE_DAYS="${SINCE_DAYS:-30}"
CUTOFF=$(date -u -v-${SINCE_DAYS}d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
      || date -u -d "${SINCE_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ)

ORGS=(
    paradigmxyz
    paradigm-operations
    foundry-rs
    alloy-rs
    commonwarexyz
    ithacaxyz
    tempoxyz
    wevm
)

if [[ $# -gt 0 ]]; then
    ORGS=("$@")
fi

clone_one() {
    local org="$1" repo="$2"
    local dest="$REPOS_DIR/$org/$repo"
    if [[ -d "$dest/.git" ]]; then
        git -C "$dest" fetch --all --prune -q 2>/dev/null && \
        git -C "$dest" reset --hard origin/HEAD -q 2>/dev/null && \
        echo "  ↻ $org/$repo" || echo "  ✗ $org/$repo (update failed)"
    else
        gh repo clone "$org/$repo" "$dest" -- --depth 1 -q 2>/dev/null && \
        echo "  ⬇ $org/$repo" || echo "  ✗ $org/$repo (clone failed)"
    fi
}
export -f clone_one
export REPOS_DIR

echo "Cloning repos pushed since $(echo "$CUTOFF" | cut -dT -f1) (${MAX_JOBS} parallel jobs)"
echo ""

total=0
for org in "${ORGS[@]}"; do
    mkdir -p "$REPOS_DIR/$org"
    echo "==> $org"

    repos=$(gh repo list "$org" --limit 200 --json name,isArchived,pushedAt \
        --jq ".[] | select(.isArchived == false) | select(.pushedAt >= \"$CUTOFF\") | .name" 2>/dev/null || true)

    if [[ -z "$repos" ]]; then
        echo "    (no recent repos)"
        echo ""
        continue
    fi

    echo "$repos" | xargs -P "$MAX_JOBS" -I {} bash -c 'clone_one "$@"' _ "$org" {}
    count=$(echo "$repos" | wc -l | tr -d ' ')
    total=$((total + count))
    echo "    ✓ $org: $count repos"
    echo ""
done

echo "Done. $total repos. Size: $(du -sh "$REPOS_DIR" | cut -f1)"
