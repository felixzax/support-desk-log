"""SQLite location and transactional schema migrations."""
import os
import sqlite3
from pathlib import Path

MIGRATIONS = (
    (
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "INSERT INTO settings VALUES ('next_number', '1'), ('starting_number', '1')",
        "CREATE TABLE tickets (number INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
        """CREATE TABLE entries (
            id INTEGER PRIMARY KEY, ticket INTEGER NOT NULL REFERENCES tickets(number)
            ON DELETE CASCADE, timestamp TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL
        )""",
        "CREATE INDEX entries_ticket ON entries(ticket, id)",
    ),
)


def data_dir() -> Path:
    """Use Windows roaming AppData and a local equivalent on Linux."""
    root = Path(os.environ.get("APPDATA") or Path.home() / ".local" / "share")
    return root / "Support Desk Log"


def connect(path: Path) -> sqlite3.Connection:
    """Open and migrate a database, or reject a schema from a newer app."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise ValueError("This database requires a newer version of Support Desk Log.")
        for index, statements in enumerate(MIGRATIONS[version:], version + 1):
            for statement in statements:
                db.execute(statement)
            db.execute(f"PRAGMA user_version = {index}")
        db.commit()
    except Exception:
        db.close()
        raise
    return db
