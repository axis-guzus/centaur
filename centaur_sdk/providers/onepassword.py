"""1Password secret manager backend.

Fetches all items from a 1Password vault using the official SDK.
Requires ``OP_SERVICE_ACCOUNT_TOKEN`` in the environment.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from onepassword.client import Client

from centaur_sdk.providers.base import SecretManagerBackend

log = logging.getLogger("secret_manager")

# Preferred field IDs to extract a secret value from a full Item, in priority order.
_FIELD_IDS = ("password", "credential", "api_key", "key", "token", "secret", "value", "notesPlain")

# Built-in field IDs that should not be treated as named sub-fields.
_BUILTIN_FIELD_IDS = frozenset(_FIELD_IDS) | frozenset(("username", "url"))

# items.get_all() supports up to 50 items per call.
_GET_ALL_BATCH = 50

def _normalize(title: str) -> str:
    """Convert a human-readable title to an ENV_VAR_NAME."""
    return re.sub(r"[^A-Z0-9]", "_", title.upper()).strip("_")


def _extract_value(item: Any) -> str | None:
    """Pick the best secret value from a fully-fetched Item's fields."""
    fields = getattr(item, "fields", []) or []
    # Try by field id first (most reliable), then by title.
    for target in _FIELD_IDS:
        for f in fields:
            if getattr(f, "id", "") == target and getattr(f, "value", ""):
                return f.value
    for target in _FIELD_IDS:
        for f in fields:
            if getattr(f, "title", "").lower() == target and getattr(f, "value", ""):
                return f.value
    # Fall back to notes.
    notes = getattr(item, "notes", "")
    if notes:
        return notes
    return None


def _extract_named_fields(item: Any) -> dict[str, str]:
    """Extract individually-named fields from a multi-field item.

    Returns a dict of {field_title: field_value} for custom fields that have
    meaningful titles (not built-in IDs like "password" or "notesPlain").
    """
    fields = getattr(item, "fields", []) or []
    result: dict[str, str] = {}
    for f in fields:
        field_title = getattr(f, "title", "").strip()
        field_value = getattr(f, "value", "")
        field_id = getattr(f, "id", "")
        if not field_title or not field_value:
            continue
        if field_id in _BUILTIN_FIELD_IDS or field_title.lower() in _BUILTIN_FIELD_IDS:
            continue
        result[field_title] = field_value
    return result


async def _list_vaults(client: Client) -> list[Any]:
    list_all = getattr(client.vaults, "list_all", None)
    if callable(list_all):
        vault_iter = await list_all()
        return [v async for v in vault_iter]
    return list(await client.vaults.list())


async def _list_items(client: Client, vault_id: str) -> list[Any]:
    list_all = getattr(client.items, "list_all", None)
    if callable(list_all):
        item_iter = await list_all(vault_id)
        return [item async for item in item_iter]
    return list(await client.items.list(vault_id))


async def _find_vault_id(client: Client, name: str) -> str:
    """Find a vault ID by name."""
    vaults = await _list_vaults(client)
    for v in vaults:
        title = getattr(v, "title", "")
        vid = getattr(v, "id", "")
        if title == name or vid == name:
            return v.id

    # If the service account only has access to one vault, prefer it.
    if len(vaults) == 1:
        only = vaults[0]
        log.warning(
            "vault '%s' not found; using only accessible vault '%s'",
            name,
            getattr(only, "title", getattr(only, "id", "<unknown>")),
        )
        return only.id

    available = ", ".join(str(getattr(v, "title", getattr(v, "id", "<unknown>"))) for v in vaults)
    raise RuntimeError(f"Vault '{name}' not found (available: {available})")


class OnePasswordBackend(SecretManagerBackend):
    """Load secrets from a 1Password vault via the SDK."""

    def __init__(self, vault_name: str | None = None) -> None:
        self._vault_name = vault_name or os.environ.get("OP_VAULT") or "ai-agents"
        self._client: Client | None = None

    async def _init_client(self) -> Client:
        token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "")
        if not token:
            raise RuntimeError("OP_SERVICE_ACCOUNT_TOKEN is not set")
        return await Client.authenticate(
            auth=token,
            integration_name="centaur-secret-manager",
            integration_version="1.0.0",
        )

    async def load_all(self) -> dict[str, str]:
        if self._client is None:
            self._client = await self._init_client()

        vault_id = await _find_vault_id(self._client, self._vault_name)
        items = await _list_items(self._client, vault_id)

        # Collect item IDs and titles from the overview list.
        overviews: list[tuple[str, str]] = []
        for item_overview in items:
            item_id = getattr(item_overview, "id", "")
            item_title = getattr(item_overview, "title", "")
            if item_id:
                overviews.append((item_id, item_title))

        # Batch-fetch full items via get_all (50 per call).
        full_items: list[Any] = []
        for i in range(0, len(overviews), _GET_ALL_BATCH):
            batch_ids = [oid for oid, _ in overviews[i : i + _GET_ALL_BATCH]]
            resp = await self._client.items.get_all(vault_id, batch_ids)
            for r in resp.individual_responses:
                if r.content is not None:
                    full_items.append(r.content)

        new_cache: dict[str, str] = {}
        for item in full_items:
            title = getattr(item, "title", "")

            # Multi-field items: each named field becomes its own cache key.
            named = _extract_named_fields(item)
            if named:
                for field_name, field_value in named.items():
                    new_cache[field_name] = field_value
                    norm = _normalize(field_name)
                    if norm != field_name:
                        new_cache[norm] = field_value

            # Single-value fallback: store under item title.
            value = _extract_value(item)
            if not value and not named:
                log.debug("skipping item %s — no resolvable field", title)
                continue
            if value:
                new_cache[title] = value
                norm = _normalize(title)
                if norm != title:
                    new_cache[norm] = value

        log.info(
            "loaded %d keys from vault '%s': %s",
            len(new_cache),
            self._vault_name,
            ", ".join(sorted(new_cache.keys())),
        )
        return new_cache
