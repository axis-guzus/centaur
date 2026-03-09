#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Slackbot entrypoint — bootstrap secrets from the firewall secret proxy.
# ---------------------------------------------------------------------------

MAX_RETRIES=30
RETRY_DELAY=2

fetch_secret() {
  local key="$1"
  curl -fsS --max-time 5 "${SECRET_MANAGER_URL}/secrets/${key}" \
    | jq -er '.value | select(type == "string" and length > 0)'
}

bootstrap_required_secrets() {
  local missing=()
  local key val attempt

  for key in "$@"; do
    [[ -n "${!key:-}" ]] || missing+=("$key")
  done

  (( ${#missing[@]} == 0 )) && return 0

  if [[ -z "${SECRET_MANAGER_URL:-}" ]]; then
    echo "FATAL: missing required secrets and SECRET_MANAGER_URL is not set: ${missing[*]}" >&2
    return 1
  fi

  for attempt in $(seq 1 "$MAX_RETRIES"); do
    local next_missing=()

    for key in "${missing[@]}"; do
      [[ -n "${!key:-}" ]] && continue

      if val="$(fetch_secret "$key")"; then
        printf -v "$key" '%s' "$val"
        export "$key"
      else
        next_missing+=("$key")
      fi
    done

    if (( ${#next_missing[@]} == 0 )); then
      return 0
    fi

    echo "Waiting for secrets (${attempt}/${MAX_RETRIES}): ${next_missing[*]}" >&2
    sleep "$RETRY_DELAY"
    missing=("${next_missing[@]}")
  done

  echo "FATAL: missing required secrets after bootstrap: ${missing[*]}" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
bootstrap_required_secrets SLACK_BOT_TOKEN SLACK_SIGNING_SECRET SLACKBOT_API_KEY DATABASE_URL

exec node server.js
