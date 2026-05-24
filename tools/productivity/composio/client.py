"""Composio tool — execute actions from 1000+ services via Composio's cloud API."""

from __future__ import annotations

from centaur_sdk import secret

# Composio user_id scopes connected accounts. "centaur" is the default for
# shared/unscoped usage; callers should pass a real user_id when accounts
# are per-user to avoid cross-tenant data leakage.
_DEFAULT_USER_ID = "centaur"


def _extract_tools(raw: list) -> list[dict]:
    """Pull name + description from Composio's OpenAI-shaped tool dicts."""
    tools = []
    for t in raw:
        if isinstance(t, dict):
            fn = t.get("function", {})
            tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
            })
    return tools


class ComposioClient:
    """Bridge to Composio's tool execution platform."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or secret("COMPOSIO_API_KEY")
        self._composio = None

    def _get_client(self):
        if self._composio is None:
            from composio import Composio

            self._composio = Composio(api_key=self._api_key)
        return self._composio

    def list_tools(self, toolkit: str, user_id: str = _DEFAULT_USER_ID) -> dict:
        """List available tools for a toolkit (e.g. 'github', 'gmail', 'slack', 'notion')."""
        c = self._get_client()
        raw = c.tools.get(user_id, toolkits=[toolkit])
        tools = _extract_tools(raw)
        return {"toolkit": toolkit, "tools": tools, "count": len(tools)}

    def search_tools(self, query: str, user_id: str = _DEFAULT_USER_ID) -> dict:
        """Search for tools across all toolkits by description."""
        c = self._get_client()
        raw = c.tools.get(user_id, search=query)
        tools = _extract_tools(raw[:20])
        return {"query": query, "tools": tools, "count": len(tools)}

    def execute(
        self,
        tool_slug: str,
        arguments: dict | None = None,
        user_id: str = _DEFAULT_USER_ID,
    ) -> dict:
        """Execute a Composio tool action.

        tool_slug examples: GITHUB_LIST_REPOS_FOR_USER, HACKERNEWS_GET_TOP_STORIES.
        Use get_tool_schema() to discover required arguments.
        """
        c = self._get_client()
        # Version check requires per-toolkit version pinning which is impractical
        # when the caller doesn't know the toolkit in advance.
        result = c.tools.execute(
            tool_slug,
            user_id=user_id,
            arguments=arguments or {},
            dangerously_skip_version_check=True,
        )
        if isinstance(result, dict):
            return {
                "successful": result.get("successful", False),
                "error": result.get("error"),
                "data": result.get("data", {}),
            }
        return {
            "successful": getattr(result, "successful", False),
            "error": getattr(result, "error", None),
            "data": getattr(result, "data", {}),
        }

    def get_tool_schema(self, tool_slug: str, user_id: str = _DEFAULT_USER_ID) -> dict:
        """Get the input/output schema for a specific tool."""
        c = self._get_client()
        raw = c.tools.get(user_id, search=tool_slug)
        for t in raw:
            if isinstance(t, dict):
                fn = t.get("function", {})
                if fn.get("name") == tool_slug:
                    return {
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {}),
                    }
        return {"error": f"Tool {tool_slug} not found"}


def _client() -> ComposioClient:
    return ComposioClient()
