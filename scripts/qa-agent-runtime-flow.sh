#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${CENTAUR_NAMESPACE:-centaur}"
REQUIRED_DEPLOYMENTS=(centaur-centaur-api)

for deployment in "${REQUIRED_DEPLOYMENTS[@]}"; do
  if ! kubectl -n "$NAMESPACE" rollout status "deploy/$deployment" --timeout=1s >/dev/null 2>&1; then
    echo "$deployment deployment is not ready in namespace $NAMESPACE. Start the local stack first." >&2
    echo "Suggested command: just up" >&2
    exit 1
  fi
done

python3 "$SCRIPT_DIR/qa_agent_runtime_flow.py" "$@"
