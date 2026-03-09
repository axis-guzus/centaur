#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Container entrypoint.
#
# Secret management is handled by the dedicated `secrets` sidecar service
# (src/secret_manager/) which caches 1Password vault contents and serves
# them over HTTP.  No 1Password bootstrap is needed here.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Resolve bootstrap secrets from the firewall's scoped secret proxy
# ---------------------------------------------------------------------------
if [[ -n "${SECRET_MANAGER_URL:-}" ]]; then
    for key in DATABASE_URL API_SECRET_KEY SLACK_SIGNING_SECRET; do
        # Skip if already set
        eval "current=\${${key}:-}"
        if [[ -n "$current" ]]; then continue; fi

        for i in $(seq 1 30); do
            val=$(curl -sf --max-time 5 "${SECRET_MANAGER_URL}/secrets/${key}" | jq -r '.value // empty' 2>/dev/null || true)
            if [[ -n "$val" ]]; then
                export "$key=$val"
                break
            fi
            echo "Waiting for ${key}... (attempt $i/30)"
            sleep 2
        done

        eval "current=\${${key}:-}"
        if [[ -z "$current" ]]; then
            echo "FATAL: Could not resolve ${key} from secret proxy" >&2
            exit 1
        fi
    done
fi

# ---------------------------------------------------------------------------
# Canonical env aliases
# Keep app code stable on canonical names while allowing legacy/box-specific
# variable names from .env or 1Password item titles.
# ---------------------------------------------------------------------------
if [[ -z "${SLACK_BOT_TOKEN:-}" && -n "${SLACK_TOKEN:-}" ]]; then
    export SLACK_BOT_TOKEN="${SLACK_TOKEN}"
fi
if [[ -z "${GITHUB_TOKEN:-}" && -n "${GH_TOKEN:-}" ]]; then
    export GITHUB_TOKEN="${GH_TOKEN}"
fi
if [[ -z "${GITHUB_TOKEN:-}" && -n "${GITHUB_PAT:-}" ]]; then
    export GITHUB_TOKEN="${GITHUB_PAT}"
fi
if [[ -z "${ANTHROPIC_API_KEY:-}" && -n "${ANTHROPIC_KEY:-}" ]]; then
    export ANTHROPIC_API_KEY="${ANTHROPIC_KEY}"
fi
if [[ -z "${ANTHROPIC_API_KEY:-}" && -n "${CLAUDE_API_KEY:-}" ]]; then
    export ANTHROPIC_API_KEY="${CLAUDE_API_KEY}"
fi

exec "$@"
