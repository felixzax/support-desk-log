"""SQLite persistence for hardware records and their manuals."""
from collections.abc import Iterator

from app.data.repository import Repository
from app.models.hardware import Hardware


class HardwareRepository:
    """Use the app database for metadata and attachment bytes."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def items(self) -> list[Hardware]:
        """Return the catalog in make and model order."""
        return [Hardware(**row) for row in self.repo.db.execute(
            "SELECT * FROM hardware ORDER BY make COLLATE NOCASE, model COLLATE NOCASE, id"
        )]

    def save(self, item: Hardware) -> int:
        """Insert or update a model and return its identifier."""
        fields = (item.kind, item.make, item.model, item.power, item.ink, item.location)
        if item.id is None:
            result = self.repo.db.execute(
                "INSERT INTO hardware(kind, make, model, power, ink, location) VALUES (?, ?, ?, ?, ?, ?)",
                fields,
            )
            return result.lastrowid
        result = self.repo.db.execute(
            "UPDATE hardware SET kind=?, make=?, model=?, power=?, ink=?, location=? WHERE id=?",
            (*fields, item.id),
        )
        if not result.rowcount:
            raise ValueError("This hardware record no longer exists.")
        return item.id

    def delete(self, identifier: int) -> None:
        """Delete a model and cascade to its manuals."""
        self.repo.db.execute("DELETE FROM hardware WHERE id = ?", (identifier,))

    def manuals(self, identifier: int) -> list[tuple[int, str, int]]:
        """List attachment metadata without reading document bytes."""
        return [tuple(row) for row in self.repo.db.execute(
            "SELECT id, name, length(content) FROM manuals WHERE hardware_id = ? ORDER BY name, id",
            (identifier,),
        )]

    def add_manual(self, identifier: int, name: str, content: bytes) -> None:
        """Store a copy of a manual against its model."""
        self.repo.db.execute(
            "INSERT INTO manuals(hardware_id, name, content) VALUES (?, ?, ?)",
            (identifier, name, content),
        )

    def read_manual(self, identifier: int, manual: int) -> bytes:
        """Load the selected document bytes."""
        row = self.repo.db.execute(
            "SELECT content FROM manuals WHERE hardware_id = ? AND id = ?", (identifier, manual)
        ).fetchone()
        if row is None:
            raise ValueError("This manual no longer exists.")
        return row[0]

    def delete_manual(self, identifier: int, manual: int) -> None:
        """Remove the selected attachment."""
        self.repo.db.execute(
            "DELETE FROM manuals WHERE hardware_id = ? AND id = ?", (identifier, manual)
        )

    def documents(self) -> Iterator[dict]:
        """Read attachments for a complete backup."""
        for row in self.repo.db.execute("SELECT * FROM manuals ORDER BY id"):
            yield dict(row)
