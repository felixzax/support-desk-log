"""Ticket validation, numbering, and timeline operations."""
from dataclasses import replace
from datetime import date, datetime

from app.data.repository import Repository
from app.models.ticket import CATEGORIES, PRIORITIES, TRANSITIONS, Ticket


def timestamp() -> str:
    """Record local wall time with its UTC offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def validate(ticket: Ticket) -> None:
    """Validate a complete ticket before it can be saved."""
    if not ticket.title.strip() or not ticket.requester.strip():
        raise ValueError("Enter an issue title and requester name.")
    if not ticket.opened:
        raise ValueError("Enter the date opened.")
    if ticket.category not in CATEGORIES or ticket.priority not in PRIORITIES or ticket.status not in TRANSITIONS:
        raise ValueError("Choose a valid category, priority and status.")
    for value in (ticket.opened, ticket.resolved, ticket.follow_up):
        if value and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use YYYY-MM-DD for dates.")
    if ticket.status in ("Resolved", "Closed") and not (ticket.resolution.strip() and ticket.resolved):
        raise ValueError("Enter a resolution summary and resolved date.")
    if ticket.resolved and ticket.resolved < ticket.opened:
        raise ValueError("The resolved date cannot be before the opened date.")
    if ticket.minutes is not None and (type(ticket.minutes) is not int or ticket.minutes < 0):
        raise ValueError("Enter a non-negative whole number of minutes.")


class Tickets:
    """Coordinate all user-facing changes with their timeline records."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def save(self, draft: Ticket) -> Ticket:
        """Create or update a ticket and log changes atomically."""
        with self.repo.transaction():
            old = self.repo.get(draft.number) if draft.number else None
            if old and draft.status != old.status and draft.status not in TRANSITIONS[old.status]:
                raise ValueError(f"Cannot change {old.status} to {draft.status}.")
            if not old and draft.status not in ("Open", "In Progress"):
                raise ValueError("New tickets start Open or In Progress.")
            resolved = draft.resolved
            if draft.status == "Resolved" and not resolved:
                resolved = date.today().isoformat()
            if old and old.status == "Closed" and draft.status == "Open":
                resolved = ""
            number = draft.number or int(self.repo.setting("next_number"))
            ticket = replace(draft, number=number, title=draft.title.strip(),
                             requester=draft.requester.strip(), resolved=resolved, updated=timestamp())
            validate(ticket)
            for related in ticket.related:
                if related == number:
                    raise ValueError("A ticket cannot be related to itself.")
                self.repo.get(related)
            self.repo.write(ticket)
            if not old:
                self.repo.set_setting("next_number", str(number + 1))
                self.repo.add_entry(number, ticket.updated, "Status", f"Created as {ticket.status}")
            else:
                if old.status != ticket.status:
                    label = "Reopened · " if old.status == "Closed" else ""
                    self.repo.add_entry(number, ticket.updated, "Status", f"{label}{old.status} → {ticket.status}")
                if old.priority != ticket.priority:
                    self.repo.add_entry(number, ticket.updated, "Priority", f"{old.priority} → {ticket.priority}")
            return ticket

    def note(self, number: int, body: str | None, entry: int | None = None) -> None:
        """Add, edit or delete a manual timeline note."""
        if body is not None and not body.strip():
            raise ValueError("Enter a log entry.")
        with self.repo.transaction():
            ticket = self.repo.get(number)
            ticket.updated = timestamp()
            if entry is None:
                self.repo.add_entry(number, ticket.updated, "Note", (body or "").strip())
            else:
                self.repo.change_entry(number, entry, body.strip() if body is not None else None)
            self.repo.write(ticket)

    def starting_number(self, number: int) -> None:
        """Set a floor while preserving every previously issued number."""
        if number < 1:
            raise ValueError("Use a positive starting number.")
        with self.repo.transaction():
            self.repo.set_setting("starting_number", str(number))
            self.repo.set_setting("next_number", str(max(number, int(self.repo.setting("next_number")))))

    def delete(self, number: int) -> None:
        """Remove a ticket and its associated timeline."""
        with self.repo.transaction():
            self.repo.delete(number)

    def load_samples(self) -> None:
        """Load explicitly labeled fictional tickets on request."""
        if any(ticket.sample for ticket in self.repo.tickets()):
            return
        today = date.today().isoformat()
        self.save(Ticket("[Sample] Demo printer offline", "Demo Requester A", today,
                         category="Printer/Scanner", sample=True))
        self.save(Ticket("[Sample] Demo app setup", "Demo Requester B", today,
                         category="Software", sample=True))

    def clear_samples(self) -> None:
        """Remove only tickets flagged as sample data."""
        with self.repo.transaction():
            for ticket in self.repo.tickets():
                if ticket.sample:
                    self.repo.delete(ticket.number)
