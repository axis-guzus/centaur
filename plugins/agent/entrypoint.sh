#!/bin/bash
set -e

HOME_DIR="$(eval echo ~)"
GITHUB_DIR="$HOME_DIR/github"
MCP_URL="${AI_V2_API_URL:-http://localhost:8000}/mcp/"
MCP_KEY="${AI_V2_API_KEY:-}"

# ── Git credentials ──────────────────────────────────────────────────────────
if [ -n "${GITHUB_TOKEN:-}" ]; then
    git config --global credential.helper store
    echo "https://oauth2:${GITHUB_TOKEN}@github.com" > "$HOME_DIR/.git-credentials"
    echo "${GITHUB_TOKEN}" | gh auth login --with-token 2>/dev/null || true
    gh auth setup-git 2>/dev/null || true
fi

# ── MCP configs for all harnesses ────────────────────────────────────────────
if [ -n "$MCP_KEY" ]; then
    # Amp
    mkdir -p "$HOME_DIR/.config/amp"
    cat > "$HOME_DIR/.config/amp/settings.json" <<EOF
{"amp.mcpServers":{"tempo-ai":{"url":"${MCP_URL}","headers":{"Authorization":"Bearer ${MCP_KEY}"}}}}
EOF

    # Claude Code
    cat > "$HOME_DIR/.claude.json" <<EOF
{"mcpServers":{"tempo-ai":{"type":"http","url":"${MCP_URL}","headers":{"Authorization":"Bearer ${MCP_KEY}"}}}}
EOF

    # Codex
    mkdir -p "$HOME_DIR/.codex"
    cat > "$HOME_DIR/.codex/config.toml" <<EOF
[mcp_servers.tempo-ai]
url = "${MCP_URL}"
EOF
fi

# ── Codex auth ───────────────────────────────────────────────────────────────
CODEX_KEY="${CODEX_API_KEY:-${OPENAI_API_KEY:-}}"
if [ -n "$CODEX_KEY" ]; then
    if command -v codex >/dev/null 2>&1; then
        echo "$CODEX_KEY" | codex login --with-api-key 2>/dev/null || true
    fi
fi

# ── Optional repo sync ──────────────────────────────────────────────────────
if [ "${SYNC_ON_START:-false}" = "true" ]; then
    for org_dir in "$GITHUB_DIR"/*/; do
        [ -d "$org_dir" ] || continue
        for repo_dir in "$org_dir"*/; do
            if [ -d "$repo_dir/.git" ]; then
                echo "Updating $(basename "$(dirname "$repo_dir")")/$(basename "$repo_dir")..."
                git -C "$repo_dir" fetch origin -q 2>/dev/null || true
                git -C "$repo_dir" reset --hard origin/HEAD -q 2>/dev/null || true
            fi
        done
    done
fi

exec "$@"
