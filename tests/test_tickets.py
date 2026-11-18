from dataclasses import replace

import pytest

from app.data.database import connect
from app.data.repository import Repository
from app.models.ticket import Ticket
from app.services.tickets import Tickets


@pytest.fixture
def service(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    yield Tickets(Repository(db))
    db.close()


def test_numbering_survives_delete_and_restart(service, tmp_path):
    service.starting_number(12)
    draft = Ticket("Printer Not Connecting", "Test Requester", "2026-01-15")
    first = service.save(draft)
    assert first.subject == "Printer Not Connecting [Ticket #12 01-15-26]"
    service.delete(first.number)
    service.starting_number(1)
    db = connect(tmp_path / "test.sqlite")
    try:
        assert Tickets(Repository(db)).save(draft).number == 13
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        db.close()


def test_transitions_and_audit(service):
    ticket = service.save(Ticket("Test issue", "Test Requester", "2026-01-15"))
    with pytest.raises(ValueError):
        service.save(replace(ticket, status="Closed"))
    ticket = service.save(replace(ticket, status="In Progress", priority="High"))
    ticket = service.save(replace(ticket, status="Waiting on User"))
    ticket = service.save(replace(ticket, status="In Progress"))
    with pytest.raises(ValueError):
        service.save(replace(ticket, status="Resolved"))
    ticket = service.save(replace(ticket, status="Resolved", resolution="Fixed"))
    assert ticket.resolved
    ticket = service.save(replace(ticket, status="Closed"))
    ticket = service.save(replace(ticket, status="Open"))
    entries = service.repo.entries(ticket.number)
    assert not ticket.resolved
    assert [entry["kind"] for entry in entries].count("Priority") == 1
    assert "Reopened" in entries[-1]["body"]
