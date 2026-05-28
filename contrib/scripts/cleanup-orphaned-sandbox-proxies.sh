#!/usr/bin/env bash
set -euo pipefail

namespace="${NAMESPACE:-centaur}"
yes=0

usage() {
  cat <<'EOF'
Usage: cleanup-orphaned-sandbox-proxies.sh [--namespace NAMESPACE] [--yes]

Deletes per-sandbox iron-proxy resources whose centaur.ai/sandbox-id label no
longer has a matching sandbox pod. Dry-run by default; pass --yes to delete.

Environment:
  NAMESPACE   Kubernetes namespace to inspect (default: centaur)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)
      namespace="${2:?missing namespace}"
      shift 2
      ;;
    --yes)
      yes=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 127
  }
}

require kubectl
require jq

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

sandbox_ids="$tmpdir/sandbox-ids"
proxy_ids="$tmpdir/proxy-ids"
orphan_ids="$tmpdir/orphan-ids"

kubectl -n "$namespace" get pods -l 'centaur.ai/managed=true' -o json \
  | jq -r '.items[].metadata.labels["centaur.ai/sandbox-id"] // empty' \
  | sort -u > "$sandbox_ids"

kubectl -n "$namespace" get pods -l 'centaur.ai/iron-proxy=true' -o json \
  | jq -r '.items[].metadata.labels["centaur.ai/sandbox-id"] // empty' \
  | sort -u > "$proxy_ids"

comm -23 "$proxy_ids" "$sandbox_ids" \
  | awk 'NF && $0 != "api"' > "$orphan_ids"

if [[ ! -s "$orphan_ids" ]]; then
  echo "No orphaned per-sandbox iron-proxy resources found in namespace '$namespace'."
  exit 0
fi

echo "Orphaned sandbox IDs in namespace '$namespace':"
sed 's/^/  /' "$orphan_ids"

delete_args=()
if [[ "$yes" -eq 0 ]]; then
  echo
  echo "Dry run only. Re-run with --yes to delete these resources."
  delete_args+=(--dry-run=server -o name)
else
  delete_args+=(-o name)
fi

while IFS= read -r sandbox_id; do
  [[ -n "$sandbox_id" ]] || continue
  selector="centaur.ai/sandbox-id=${sandbox_id}"
  echo
  echo "Cleaning resources for sandbox-id=$sandbox_id"
  kubectl -n "$namespace" delete \
    pod,service,configmap,secret,networkpolicy \
    -l "$selector" \
    "${delete_args[@]}" \
    --ignore-not-found
done < "$orphan_ids"
