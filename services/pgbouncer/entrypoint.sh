#!/usr/bin/env sh
set -e

# Fetch DATABASE_URL from the firewall's scoped secret proxy.
# The edoburu/pgbouncer image reads DATABASE_URL to auto-generate
# pgbouncer.ini and userlist.txt, so we must resolve it before
# the upstream entrypoint runs.

if [ -n "$SECRET_MANAGER_URL" ] && [ -z "$DATABASE_URL" ]; then
  MAX_RETRIES=30
  RETRY=0
  while [ $RETRY -lt $MAX_RETRIES ]; do
    val=$(curl -sf --max-time 5 "${SECRET_MANAGER_URL}/secrets/DATABASE_URL" | jq -r '.value // empty' 2>/dev/null || true)
    if [ -n "$val" ]; then
      export DATABASE_URL="$val"
      echo "Resolved DATABASE_URL from secret proxy"
      break
    fi
    RETRY=$((RETRY + 1))
    echo "Waiting for DATABASE_URL secret... (attempt $RETRY/$MAX_RETRIES)"
    sleep 2
  done

  if [ -z "$DATABASE_URL" ]; then
    echo "FATAL: Could not resolve DATABASE_URL from secret proxy after $MAX_RETRIES attempts" >&2
    exit 1
  fi
fi

# Hand off to the upstream edoburu/pgbouncer entrypoint
exec /entrypoint.sh "$@"
