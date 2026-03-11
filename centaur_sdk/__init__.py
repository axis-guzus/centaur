"""Centaur SDK — lightweight toolkit for building Centaur-compatible tools.

Public API:
    secret(key)       — resolve a secret via the pluggable backend
    Table             — Rich table (re-export for CLI tools)
    render_text_table — plain-text table renderer
    SecretBackend     — ABC for custom secret backends
    configure / get_backend / auto_configure — backend lifecycle

Server-side providers (``centaur_sdk.providers``):
    SecretManagerBackend    — ABC for secret manager storage backends
    OnePasswordBackend      — 1Password vault backend (requires ``onepassword`` extra)
    EnvSecretManagerBackend — environment-variable backend
"""

from __future__ import annotations

from centaur_sdk.cli_tables import Table, render_text_table
from centaur_sdk.tool_sdk import (
    ToolContext,
    get_tool_context,
    reset_tool_context,
    secret,
    set_tool_context,
)

__all__ = [
    "Table",
    "ToolContext",
    "get_tool_context",
    "render_text_table",
    "reset_tool_context",
    "secret",
    "set_tool_context",
]
