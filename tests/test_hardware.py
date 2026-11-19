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
        printer = catalog.save(Hardware(
            "Printer", "Test make", "Test model", "IEC C13", "T-123", location=" Room 204 "
        ))
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
        restored = catalog.search("t-123 room 204")[0]
        assert restored.id == printer
        assert restored.location == "Room 204"
        manual, name, size = storage.manuals(printer)[0]
        assert (name, size) == ("guide.txt", len(content))
        catalog.save_copy(printer, manual, file)
        assert file.read_bytes() == content
        service = Tickets(repo)
        assert service.save(Ticket("Ticket after restore", "Test requester", "2026-01-15")).number == 1
    finally:
        db.close()


def test_portable_backup_restores_on_another_computer(tmp_path):
    source_db = connect(tmp_path / "old-computer" / "tickets.sqlite3")
    target_db = connect(tmp_path / "new-computer" / "tickets.sqlite3")
    try:
        source = Repository(source_db)
        target = Repository(target_db)
        source_tickets = Tickets(source)
        ticket = source_tickets.save(Ticket(
            "Print driver", "Test requester", "2026-01-15", operating_system="Windows 11"
        ))
        source_tickets.note(ticket.number, "Installed driver")
        hardware = Catalog(HardwareRepository(source))
        printer = hardware.save(Hardware("Printer", "Test", "P100", location="Room 204"))
        manual = tmp_path / "guide.txt"
        manual.write_bytes(b"Printer guide")
        hardware.attach(printer, manual)
        manual.unlink()

        source_archive = Archive(source, tmp_path / "old-computer" / "backups")
        portable = tmp_path / "usb-drive" / "transfer.json"
        assert source_archive.export(portable) == portable
        assert not source_archive.directory.exists()

        target_tickets = Tickets(target)
        target_tickets.save(Ticket("Earlier local ticket", "Test requester", "2026-01-15"))
        target_archive = Archive(target, tmp_path / "new-computer" / "backups")
        target_archive.restore(portable)
        assert target.get(ticket.number).operating_system == "Windows 11"
        assert target.entries(ticket.number)[-1]["body"] == "Installed driver"
        target_hardware = HardwareRepository(target)
        assert target_hardware.items()[0].location == "Room 204"
        manual_id, _, _ = target_hardware.manuals(printer)[0]
        assert target_hardware.read_manual(printer, manual_id) == b"Printer guide"
        previous, = target_archive.directory.glob("*.json")
        assert json.loads(previous.read_text(encoding="utf-8"))["tickets"][0]["title"] == "Earlier local ticket"
    finally:
        source_db.close()
        target_db.close()
