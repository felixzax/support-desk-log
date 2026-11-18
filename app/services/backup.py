"""Versioned JSON backups with atomic replacement and bounded retention."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from app.data.repository import Repository
from app.models.ticket import Ticket
from app.services.tickets import validate


class Archive:
    """Save and restore consistent snapshots of all local application data."""

    def __init__(self, repo: Repository, directory: Path) -> None:
        self.repo = repo
        self.directory = directory

    def backup(self) -> Path:
        """Write a snapshot and keep the latest ten successful files."""
        with self.repo.transaction(write=False):
            tickets = self.repo.tickets()
            state = {
                "version": 1,
                "tickets": [dict(ticket.payload(), number=ticket.number) for ticket in tickets],
                "entries": [entry for ticket in tickets for entry in self.repo.entries(ticket.number)],
                "settings": dict(self.repo.db.execute("SELECT key, value FROM settings")),
            }
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"support-desk-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                handle.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        for old in sorted(self.directory.glob("support-desk-*.json"), reverse=True)[10:]:
            old.unlink(missing_ok=True)
        return path

    def restore(self, path: Path) -> None:
        """Validate the snapshot before replacing records in a single transaction."""
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state["version"] != 1:
                raise ValueError("Unsupported backup version.")
            tickets = [Ticket(**record) for record in state["tickets"]]
            numbers = {ticket.number for ticket in tickets}
            if len(numbers) != len(tickets) or any(type(n) is not int or n < 1 for n in numbers):
                raise ValueError("Invalid ticket numbers.")
            for ticket in tickets:
                validate(ticket)
                datetime.fromisoformat(ticket.updated)
                if ticket.number in ticket.related or not numbers.issuperset(ticket.related):
                    raise ValueError("Invalid related tickets.")
            entries = sorted(state["entries"], key=lambda entry: entry["id"])
            for entry in entries:
                if entry["ticket"] not in numbers or entry["kind"] not in ("Note", "Status", "Priority"):
                    raise ValueError("Invalid timeline entry.")
                datetime.fromisoformat(entry["timestamp"])
                if not isinstance(entry["body"], str):
                    raise ValueError("Invalid timeline text.")
            settings = state["settings"]
            if any(not isinstance(value, str) for value in settings.values()):
                raise ValueError("Invalid settings.")
            next_number = int(settings["next_number"])
            if next_number <= max(numbers, default=0) or int(settings["starting_number"]) < 1:
                raise ValueError("Invalid numbering settings.")
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Cannot read this backup. {error}") from error

        self.backup()
        with self.repo.transaction():
            current_next = int(self.repo.setting("next_number"))
            self.repo.db.execute("DELETE FROM tickets")
            self.repo.db.execute("DELETE FROM settings")
            for key, value in settings.items():
                self.repo.set_setting(key, value)
            self.repo.set_setting("next_number", str(max(next_number, current_next)))
            for ticket in tickets:
                self.repo.write(ticket)
            for entry in entries:
                self.repo.add_entry(entry["ticket"], entry["timestamp"], entry["kind"], entry["body"])
