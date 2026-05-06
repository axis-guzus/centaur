#!/usr/bin/env bash
set -euo pipefail

: "${SLACK_BOT_TOKEN:?SLACK_BOT_TOKEN is required}"
: "${SLACK_SIGNING_SECRET:?SLACK_SIGNING_SECRET is required}"
: "${SLACKBOT_API_KEY:?SLACKBOT_API_KEY is required}"
: "${DATABASE_URL:?DATABASE_URL is required}"

exec "$@"
