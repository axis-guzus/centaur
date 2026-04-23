"""Client for querying Shift notes from the pmadmin database."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .database import get_db

class NoteType(str, Enum):
    OPPORTUNITY = "OPPORTUNITY"
    PORTCO_UPDATE = "PORTCO_UPDATE"
    PORTCO_REVIEW = "PORTCO_REVIEW"
    TALENT = "TALENT"
    GTM = "GTM"
    DESIGN = "DESIGN"
    LEGAL_POLICY = "LEGAL_POLICY"
    OTHER = "OTHER"
    NONE = "NONE"
    INVESTOR_RELATIONS = "INVESTOR_RELATIONS"
    MARKETING = "MARKETING"

@dataclass
class Note:
    """A Shift note."""

    id: str
    title: str | None
    notes: str
    note_type: str | None
    source: str
    created_at: datetime
    updated_at: datetime
    created_by_id: str
    created_by_name: str | None = None
    record_date: datetime | None = None
    organizations: list[str] | None = None
    people: list[str] | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Note":
        return cls(
            id=row["id"],
            title=row.get("title"),
            notes=row.get("notes", ""),
            note_type=row.get("noteType"),
            source=row.get("source", "MANUAL"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by_id=row["created_by_id"],
            created_by_name=row.get("created_by_name"),
            record_date=row.get("record_date"),
            organizations=row.get("organizations"),
            people=row.get("people"),
        )

class NotesClient:
    """Client for querying Shift notes."""

    def __init__(self):
        self.db = get_db()

    def list_notes(
        self,
        note_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[Note]:
        """List notes with optional filtering."""
        order_dir = "DESC" if descending else "ASC"

        sql = """
            SELECT
                n.id, n.title, n.notes, n."noteType", n.source,
                n.created_at, n.updated_at, n.created_by_id, n.record_date,
                p."fullName" as created_by_name
            FROM "Notes" n
            LEFT JOIN "User" u ON n.created_by_id = u.id
            LEFT JOIN "Person" p ON u."personId" = p.id
        """
        params: list[Any] = []

        if note_type:
            sql += ' WHERE n."noteType" = %s'
            params.append(note_type)

        sql += f' ORDER BY n."{order_by}" {order_dir} LIMIT %s OFFSET %s'
        params.extend([limit, offset])

        rows = self.db.query(sql, tuple(params))
        return [Note.from_row(r) for r in rows]

    def search_notes(
        self,
        query: str,
        note_type: str | None = None,
        limit: int = 20,
    ) -> list[Note]:
        """Full-text search notes using PostgreSQL tsvector."""
        sql = """
            SELECT
                n.id, n.title, n.notes, n."noteType", n.source,
                n.created_at, n.updated_at, n.created_by_id, n.record_date,
                p."fullName" as created_by_name,
                ts_rank(n.notes_search, plainto_tsquery('english', %s)) +
                ts_rank(n.title_search, plainto_tsquery('english', %s)) * 2 as rank
            FROM "Notes" n
            LEFT JOIN "User" u ON n.created_by_id = u.id
            LEFT JOIN "Person" p ON u."personId" = p.id
            WHERE (n.notes_search @@ plainto_tsquery('english', %s)
                   OR n.title_search @@ plainto_tsquery('english', %s)
                   OR n.title ILIKE %s
                   OR n.notes ILIKE %s)
        """
        like_query = f"%{query}%"
        params: list[Any] = [query, query, query, query, like_query, like_query]

        if note_type:
            sql += ' AND n."noteType" = %s'
            params.append(note_type)

        sql += " ORDER BY rank DESC, n.created_at DESC LIMIT %s"
        params.append(limit)

        rows = self.db.query(sql, tuple(params))
        return [Note.from_row(r) for r in rows]

    def get_note(self, note_id: str) -> Note | None:
        """Get a single note by ID."""
        sql = """
            SELECT
                n.id, n.title, n.notes, n."noteType", n.source,
                n.created_at, n.updated_at, n.created_by_id, n.record_date,
                p."fullName" as created_by_name
            FROM "Notes" n
            LEFT JOIN "User" u ON n.created_by_id = u.id
            LEFT JOIN "Person" p ON u."personId" = p.id
            WHERE n.id = %s
        """
        row = self.db.query_one(sql, (note_id,))
        if row:
            return Note.from_row(row)
        return None

    def get_note_with_relations(self, note_id: str) -> dict[str, Any] | None:
        """Get a note with its related organizations and people."""
        note = self.get_note(note_id)
        if not note:
            return None

        # Get related organizations
        orgs = self.db.query(
            """
            SELECT o.name FROM "Organization" o
            JOIN "_NotesToOrganization" nto ON o.id = nto."B"
            WHERE nto."A" = %s
            """,
            (note_id,),
        )

        # Get related people
        people = self.db.query(
            """
            SELECT p."fullName" as name FROM "Person" p
            JOIN "_NotesToPerson" ntp ON p.id = ntp."B"
            WHERE ntp."A" = %s
            """,
            (note_id,),
        )

        return {
            "note": note,
            "organizations": [o["name"] for o in orgs],
            "people": [p["name"] for p in people],
        }

    def get_notes_for_organization(
        self,
        org_name: str,
        limit: int = 20,
    ) -> list[Note]:
        """Get notes related to an organization."""
        sql = """
            SELECT
                n.id, n.title, n.notes, n."noteType", n.source,
                n.created_at, n.updated_at, n.created_by_id, n.record_date,
                p."fullName" as created_by_name
            FROM "Notes" n
            LEFT JOIN "User" u ON n.created_by_id = u.id
            LEFT JOIN "Person" p ON u."personId" = p.id
            JOIN "_NotesToOrganization" nto ON n.id = nto."A"
            JOIN "Organization" o ON nto."B" = o.id
            WHERE o.name ILIKE %s
            ORDER BY n.created_at DESC
            LIMIT %s
        """
        rows = self.db.query(sql, (f"%{org_name}%", limit))
        return [Note.from_row(r) for r in rows]

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics about notes."""
        type_counts = self.db.query(
            """
            SELECT "noteType", COUNT(*) as count
            FROM "Notes"
            GROUP BY "noteType"
            ORDER BY count DESC
            """
        )

        source_counts = self.db.query(
            """
            SELECT source, COUNT(*) as count
            FROM "Notes"
            GROUP BY source
            ORDER BY count DESC
            """
        )

        total = self.db.query_one('SELECT COUNT(*) as count FROM "Notes"')

        recent = self.db.query_one(
            """
            SELECT COUNT(*) as count FROM "Notes"
            WHERE created_at > NOW() - INTERVAL '30 days'
            """
        )

        return {
            "total": total["count"] if total else 0,
            "last_30_days": recent["count"] if recent else 0,
            "by_type": {r["noteType"]: r["count"] for r in type_counts},
            "by_source": {r["source"]: r["count"] for r in source_counts},
        }

    def get_authors(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get top note authors."""
        return self.db.query(
            """
            SELECT p."fullName" as name, u.email, COUNT(*) as note_count
            FROM "Notes" n
            JOIN "User" u ON n.created_by_id = u.id
            JOIN "Person" p ON u."personId" = p.id
            GROUP BY u.id, p."fullName", u.email
            ORDER BY note_count DESC
            LIMIT %s
            """,
            (limit,),
        )

# Singleton
_client: NotesClient | None = None

def get_notes_client() -> NotesClient:
    """Get the singleton notes client."""
    global _client
    if _client is None:
        _client = NotesClient()
    return _client
