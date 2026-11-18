import csv
from datetime import date

from openpyxl import load_workbook

from app.data.database import connect
from app.data.repository import Repository
from app.models.ticket import Ticket
from app.services.backup import Archive
from app.services.export import export, monthly
from app.services.search import browse
from app.services.tickets import Tickets


def test_search_spans_past_and_manual_notes(tmp_path):
    db = connect(tmp_path / "test.db")
    try:
        repo = Repository(db)
        service = Tickets(repo)
        service.save(Ticket("Another issue", "Other requester", "2026-01-12"))
        past = service.save(Ticket("Display issue", "Example User", "2026-01-10",
                                   status="In Progress", department="Accounts", job="Advisor"))
        past.status = "Resolved"
        past.resolution = "Replaced adapter"
        past.resolved = "2026-01-11"
        service.save(past)
        service.note(past.number, "Confirmed working")
        assert [t.number for t in browse(repo, repo.tickets(), query="advisor confirmed")] == [past.number]
        assert [t.number for t in browse(repo, repo.tickets(), requester="example user")] == [past.number]
        assert past.number not in [t.number for t in browse(repo, repo.tickets())]
    finally:
        db.close()


def test_export_preserves_formats_and_dates(tmp_path):
    tickets = [Ticket("=example", "Test User", "2026-01-15", number=1, minutes=42),
               Ticket("Past issue", "Test User", "2025-12-01", number=2)]
    start = end = date(2026, 1, 15)
    csv_path, xlsx_path = tmp_path / "tickets.csv", tmp_path / "tickets.xlsx"
    assert export(tickets, csv_path, start, end) == 1
    assert export(tickets, xlsx_path, start, end) == 1
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        row, = csv.DictReader(handle)
        assert row["Title"] == "'=example"
        assert row["Minutes spent"] == "42"
    workbook = load_workbook(xlsx_path)
    assert workbook.active["B2"].data_type == "s"
    assert workbook.active["L2"].value == 42
    workbook.close()
    assert "Tickets opened · 1" in monthly(tickets, start)


def test_backup_retention_restore_and_numbering(tmp_path):
    db = connect(tmp_path / "test.db")
    try:
        repo = Repository(db)
        service = Tickets(repo)
        archive = Archive(repo, tmp_path / "backups")
        draft = Ticket("Sample issue", "Test requester", "2026-01-15")
        original = service.save(draft)
        service.note(original.number, "Keep this note")
        for _ in range(11):
            path = archive.backup()
        assert len(list(archive.directory.glob("*.json"))) == 10
        service.delete(original.number)
        assert service.save(draft).number == 2
        archive.restore(path)
        assert [ticket.number for ticket in repo.tickets()] == [1]
        assert repo.entries(1)[-1]["body"] == "Keep this note"
        assert service.save(draft).number == 3
    finally:
        db.close()
