"""Plugin SDK — what plugin authors import."""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PluginContext:
    name: str
    secrets: dict[str, str] = field(default_factory=dict)


_plugin_ctx: ContextVar[PluginContext] = ContextVar("_plugin_ctx")


def set_plugin_context(ctx: PluginContext) -> Any:
    return _plugin_ctx.set(ctx)


def reset_plugin_context(token: Any) -> None:
    _plugin_ctx.reset(token)


def get_plugin_context() -> PluginContext:
    return _plugin_ctx.get()


def secret(key: str, default: str | None = None) -> str:
    """Get a secret. Resolution order: plugin context → os.environ.

    This allows secrets to be defined centrally in one root .env file,
    overridden per-plugin, or injected via environment (Docker/k8s/sops/1pw).
    Works standalone (no plugin context) by falling back to os.environ.
    """
    # 1. Check plugin context if available (server mode)
    try:
        ctx = _plugin_ctx.get()
        val = ctx.secrets.get(key)
        if val is not None:
            return val
    except LookupError:
        pass
    # 2. Fall back to os.environ (standalone CLI, Docker, k8s, sops, 1pw)
    val = os.environ.get(key)
    if val is not None:
        return val
    if default is not None:
        return default
    ctx_name = ""
    try:
        ctx_name = f" for plugin '{_plugin_ctx.get().name}'"
    except LookupError:
        pass
    raise KeyError(f"Missing secret '{key}'{ctx_name}")


def plugin_tool(*, name: str | None = None):
    """Decorator to mark an async function as a plugin tool."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__plugin_tool__ = name or fn.__name__  # type: ignore[attr-defined]
        return fn

    return decorator
