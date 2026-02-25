FROM ubuntu:24.04 AS base

# System deps
RUN apt-get update && apt-get install -y \
    git curl wget build-essential pkg-config \
    libssl-dev python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for TS repos)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (for Rust repos)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Amp CLI
RUN curl -fsSL https://ampcode.com/install.sh | bash

# Repos directory
RUN mkdir -p /repos

# Copy pre-cloned repos (populated by repo_sync)
COPY repos/ /repos/

# API config
ENV AI_V2_API_URL="http://localhost:8000"

# MCP config dirs (populated by entrypoint from AI_V2_API_KEY env)
RUN mkdir -p /root/.config/amp /root/.codex

# Working directory
WORKDIR /repos

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
