"""Persistence and transaction boundaries for tickets and log entries."""
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.models.ticket import Ticket


class Repository:
    """Store ticket records and their associated timeline."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    @contextmanager
    def transaction(self, write: bool = True) -> Iterator[None]:
        """Roll back the entire operation if a statement fails."""
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        with self.db:
            yield

    def setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))

    def tickets(self) -> list[Ticket]:
        return [self.decode(row) for row in self.db.execute("SELECT * FROM tickets ORDER BY number DESC")]

    @staticmethod
    def decode(row: sqlite3.Row) -> Ticket:
        payload = json.loads(row["payload"])
        payload["related"] = tuple(payload.get("related", ()))
        return Ticket(number=row["number"], **payload)

    def get(self, number: int) -> Ticket:
        row = self.db.execute("SELECT * FROM tickets WHERE number = ?", (number,)).fetchone()
        if row is None:
            raise ValueError("This ticket no longer exists.")
        return self.decode(row)

    def write(self, ticket: Ticket) -> None:
        self.db.execute(
            "INSERT INTO tickets VALUES (?, ?) ON CONFLICT(number) DO UPDATE SET payload = excluded.payload",
            (ticket.number, json.dumps(ticket.payload(), ensure_ascii=False)),
        )

    def delete(self, number: int) -> None:
        self.db.execute("DELETE FROM tickets WHERE number = ?", (number,))
        for ticket in self.tickets():
            if number in ticket.related:
                ticket.related = tuple(item for item in ticket.related if item != number)
                self.write(ticket)

    def entries(self, number: int) -> list[dict]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM entries WHERE ticket = ? ORDER BY id", (number,)
        )]

    def add_entry(self, number: int, timestamp: str, kind: str, body: str) -> None:
        self.db.execute(
            "INSERT INTO entries(ticket, timestamp, kind, body) VALUES (?, ?, ?, ?)",
            (number, timestamp, kind, body),
        )

    def change_entry(self, number: int, entry: int, body: str | None) -> None:
        where = " WHERE ticket = ? AND id = ? AND kind = 'Note'"
        if body is None:
            self.db.execute("DELETE FROM entries" + where, (number, entry))
        else:
            self.db.execute("UPDATE entries SET body = ?" + where, (body, number, entry))
