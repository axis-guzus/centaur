#!/bin/bash
set -e

MCP_URL="${AI_V2_API_URL:-http://localhost:8000}/mcp/"
MCP_KEY="${AI_V2_API_KEY:-}"

# Write MCP configs for all harnesses
if [ -n "$MCP_KEY" ]; then
    # Amp
    cat > /root/.config/amp/settings.json <<EOF
{"amp.mcpServers":{"tempo-ai":{"url":"${MCP_URL}","headers":{"Authorization":"Bearer ${MCP_KEY}"}}}}
EOF

    # Claude Code
    cat > /root/.claude.json <<EOF
{"mcpServers":{"tempo-ai":{"type":"http","url":"${MCP_URL}","headers":{"Authorization":"Bearer ${MCP_KEY}"}}}}
EOF

    # Codex
    cat > /root/.codex/config.toml <<EOF
[mcp_servers.tempo-ai]
command = "npx"
args = ["-y", "mcp-remote@latest", "${MCP_URL}"]
env = { "MCP_HEADERS" = "{\"Authorization\": \"Bearer ${MCP_KEY}\"}" }
EOF
fi

# Optional repo sync
if [ "${SYNC_ON_START:-false}" = "true" ]; then
    for dir in /repos/tempoxyz/*/; do
        if [ -d "$dir/.git" ]; then
            echo "Updating $(basename "$dir")..."
            cd "$dir" && git fetch origin && git reset --hard origin/HEAD 2>/dev/null || true
            cd /repos
        fi
    done
fi

exec "$@"
