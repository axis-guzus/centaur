#!/bin/bash
set -e

HOME_DIR="$(eval echo ~)"

# ── CRITICAL PATH: MCP configs (must complete before first exec) ─────────────
export MCP_URL="${AI_V2_API_URL:-http://localhost:8000}/mcp/"
export MCP_KEY="${AI_V2_API_KEY:-}"
if [ -n "$MCP_KEY" ]; then
    envsubst '${MCP_URL} ${MCP_KEY}' < "$HOME_DIR/.config/amp/settings.json.tmpl" > "$HOME_DIR/.config/amp/settings.json"
    envsubst '${MCP_URL} ${MCP_KEY}' < "$HOME_DIR/.claude.json.tmpl" > "$HOME_DIR/.claude.json"
    envsubst '${MCP_URL}'            < "$HOME_DIR/.codex/config.toml.tmpl" > "$HOME_DIR/.codex/config.toml"
fi

# ── Writable worktree (must complete before first exec) ──────────────────────
if [ -n "${AGENT_REPO:-}" ] && [ -d "$HOME_DIR/github/$AGENT_REPO/.git" ]; then
    BRANCH="agent-$(date +%s)"
    git -C "$HOME_DIR/github/$AGENT_REPO" worktree add "$HOME_DIR/workspace" -b "$BRANCH" HEAD --quiet
fi
[ -f "$HOME_DIR/AGENTS.md" ] && [ -d "$HOME_DIR/workspace" ] && cp "$HOME_DIR/AGENTS.md" "$HOME_DIR/workspace/AGENTS.md" 2>/dev/null || true

# Signal readiness — container is safe for docker exec
touch "$HOME_DIR/.ready"

# ── NON-CRITICAL: background slow auth tasks ─────────────────────────────────
{
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        git config --global credential.helper store
        echo "https://oauth2:${GITHUB_TOKEN}@github.com" > "$HOME_DIR/.git-credentials"
        echo "${GITHUB_TOKEN}" | gh auth login --with-token 2>/dev/null || true
        gh auth setup-git 2>/dev/null || true
    fi
    CODEX_KEY="${CODEX_API_KEY:-${OPENAI_API_KEY:-}}"
    if [ -n "$CODEX_KEY" ]; then
        echo "$CODEX_KEY" | codex login --with-api-key 2>/dev/null || true
    fi
} &

exec "$@"
