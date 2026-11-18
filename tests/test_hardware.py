"""Check catalog migration, manual storage, and backup compatibility."""
import json
import sqlite3

from app.data.database import MIGRATIONS, connect
from app.data.hardware import HardwareRepository
from app.data.repository import Repository
from app.models.hardware import Hardware
from app.models.ticket import Ticket
from app.services.backup import Archive
from app.services.hardware import Catalog
from app.services.tickets import Tickets


def test_existing_database_and_legacy_backup_keep_hardware(tmp_path):
    path = tmp_path / "existing.db"
    with sqlite3.connect(path) as old_db:
        for statement in MIGRATIONS[0]:
            old_db.execute(statement)
        old_db.execute("PRAGMA user_version = 1")
        ticket = Ticket("Existing issue", "Test requester", "2026-01-15", updated="2026-01-15T10:00:00")
        old_db.execute("INSERT INTO tickets VALUES (1, ?)", (json.dumps(ticket.payload()),))
        old_db.execute("UPDATE settings SET value='2' WHERE key='next_number'")
    old_db.close()
    db = connect(path)
    try:
        repo = Repository(db)
        storage = HardwareRepository(repo)
        catalog = Catalog(storage)
        identifier = catalog.save(Hardware(" Computer ", "Test make", "Test model", "65 W USB-C"))
        assert repo.get(1).title == "Existing issue"
        assert catalog.search("computer usb-c")[0].id == identifier
        legacy = tmp_path / "legacy.json"
        legacy.write_text(json.dumps({
            "version": 1, "tickets": [dict(ticket.payload(), number=1)],
            "entries": [], "settings": {"next_number": "2", "starting_number": "1"},
        }), encoding="utf-8")
        Archive(repo, tmp_path / "backups").restore(legacy)
        assert repo.get(1).title == "Existing issue"
        assert len(storage.items()) == 1
    finally:
        db.close()


def test_manual_attachment_survives_source_removal_and_restore(tmp_path):
    db = connect(tmp_path / "test.db")
    try:
        repo = Repository(db)
        storage = HardwareRepository(repo)
        catalog = Catalog(storage)
        printer = catalog.save(Hardware("Printer", "Test make", "Test model", "IEC C13", "T-123"))
        file = tmp_path / "guide.txt"
        content = b"Example printer instructions."
        file.write_bytes(content)
        catalog.attach(printer, file)
        file.unlink()
        archive = Archive(repo, tmp_path / "backups")
        snapshot = archive.backup()
        storage.delete(printer)
        assert storage.manuals(printer) == []
        archive.restore(snapshot)
        assert catalog.search("t-123")[0].id == printer
        manual, name, size = storage.manuals(printer)[0]
        assert (name, size) == ("guide.txt", len(content))
        catalog.save_copy(printer, manual, file)
        assert file.read_bytes() == content
        service = Tickets(repo)
        assert service.save(Ticket("Ticket after restore", "Test requester", "2026-01-15")).number == 1
    finally:
        db.close()
