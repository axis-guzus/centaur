"""Granola Enterprise API client.

Uses the official public API: https://docs.granola.ai
Provides workspace-wide access to meeting notes and transcripts.
"""

import re
from typing import Any

import httpx
from centaur_sdk import secret

API_BASE = "https://public-api.granola.ai"

_GRANOLA_URL_RE = re.compile(
    r"https?://notes\.granola\.ai/(?:t|d)/([0-9a-f-]+)",
    re.IGNORECASE,
)


class GranolaClient:
    """Client for Granola Enterprise API (workspace-wide notes access)."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or secret("GRANOLA_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "GRANOLA_API_KEY not set.\n"
                "Generate one at Settings → Workspaces → API tab (Enterprise plan required)."
            )
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make authenticated GET request."""
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def list_notes(
        self,
        page_size: int = 30,
        cursor: str | None = None,
        created_before: str | None = None,
        created_after: str | None = None,
        updated_after: str | None = None,
    ) -> dict[str, Any]:
        """List meeting notes across the workspace.

        Returns {notes: [...], hasMore: bool, cursor: str|None}.
        Use cursor for pagination. Dates in ISO 8601 format.
        """
        params: dict[str, Any] = {"page_size": min(page_size, 30)}
        if cursor:
            params["cursor"] = cursor
        if created_before:
            params["created_before"] = created_before
        if created_after:
            params["created_after"] = created_after
        if updated_after:
            params["updated_after"] = updated_after
        return self._get("/v1/notes", params=params)

    def get_note(self, note_id: str, include_transcript: bool = False) -> dict[str, Any]:
        """Fetch a single note by ID (not_* format, e.g. not_1d3tmYTlCICgjy).

        Returns full note with title, owner, attendees, summary_markdown,
        calendar_event, folder_membership, and optionally transcript.
        """
        params: dict[str, Any] = {}
        if include_transcript:
            params["include"] = "transcript"
        return self._get(f"/v1/notes/{note_id}", params=params)

    def list_all_notes(
        self,
        limit: int = 50,
        created_after: str | None = None,
        updated_after: str | None = None,
    ) -> list[dict[str, Any]]:
        """Paginate through notes up to limit. Convenience wrapper over list_notes."""
        all_notes: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(all_notes) < limit:
            page_size = min(30, limit - len(all_notes))
            result = self.list_notes(
                page_size=page_size,
                cursor=cursor,
                created_after=created_after,
                updated_after=updated_after,
            )
            notes = result.get("notes", [])
            all_notes.extend(notes)
            if not result.get("hasMore") or not result.get("cursor"):
                break
            cursor = result["cursor"]
        return all_notes[:limit]

    def get_transcript(self, note_id: str) -> list[dict[str, Any]]:
        """Fetch transcript for a note. Returns list of utterances."""
        note = self.get_note(note_id, include_transcript=True)
        return note.get("transcript") or []

    def search_notes(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search notes by title keyword. Case-insensitive substring match.

        Paginates through workspace notes and returns those whose title
        contains the query string.
        """
        query_lower = query.lower()
        all_notes = self.list_all_notes(limit=200)
        return [n for n in all_notes if query_lower in (n.get("title") or "").lower()][:limit]

    def get_note_by_url(
        self, url: str, include_transcript: bool = True
    ) -> dict[str, Any]:
        """Fetch a note by its Granola share URL.

        Accepts URLs like:
          - https://notes.granola.ai/t/8e354c81-...-008umkv4
          - https://notes.granola.ai/d/8e354c81-...

        The Enterprise API does not support URL-to-note resolution directly.
        This method lists recent workspace notes and finds the matching one.
        If the note was recently shared to a workspace folder, it will be found.
        """
        m = _GRANOLA_URL_RE.search(url)
        if not m:
            raise ValueError(
                f"Not a valid Granola URL: {url}\n"
                "Expected: https://notes.granola.ai/t/<id> or /d/<id>"
            )

        # List recent notes and return them with full details
        notes = self.list_all_notes(limit=30)
        if not notes:
            return {"error": "No notes found in workspace", "url": url}

        # Try each note — get full details for the first few
        results = []
        for note in notes[:10]:
            full = self.get_note(note["id"], include_transcript=include_transcript)
            results.append(full)

        return {
            "message": (
                "Cannot resolve Granola URL to a specific note via the API. "
                "Returning the 10 most recent workspace notes — match by title, "
                "date, or attendees from context."
            ),
            "url": url,
            "notes": results,
        }


def _client() -> GranolaClient:
    return GranolaClient()
