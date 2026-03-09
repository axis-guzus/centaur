#!/usr/bin/env sh
set -e

# Fetch bootstrap secrets from the firewall's scoped secret proxy
if [ -n "$SECRET_MANAGER_URL" ]; then
  MAX_RETRIES=30
  for key in AUTH_COOKIE_KEY UI_PASSWORD; do
    eval current=\$$key
    if [ -n "$current" ]; then continue; fi

    RETRY=0
    while [ $RETRY -lt $MAX_RETRIES ]; do
      val=$(wget -qO- --timeout=5 "${SECRET_MANAGER_URL}/secrets/${key}" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('value',''))" 2>/dev/null || true)
      if [ -n "$val" ]; then
        export "$key=$val"
        break
      fi
      RETRY=$((RETRY + 1))
      echo "Waiting for ${key}... (attempt $RETRY/$MAX_RETRIES)"
      sleep 2
    done

    eval current=\$$key
    if [ -z "$current" ]; then
      echo "FATAL: Could not resolve ${key} from secret proxy" >&2
      exit 1
    fi
  done
fi

exec "$@"
