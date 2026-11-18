"""Cross-ticket search, list filtering, and workload counts."""
from datetime import date, timedelta

from app.data.repository import Repository
from app.models.ticket import CURRENT, PRIORITIES, Ticket

SEARCH_FIELDS = ("title", "requester", "job", "department", "summary", "resolution")


def browse(repo: Repository, tickets: list[Ticket], *, tab: str = "CURRENT", query: str = "",
           requester: str = "", priority: str = "All priorities", oldest: bool = False,
           priority_sort: bool = False) -> list[Ticket]:
    """Apply filters. Text search and requester history span all statuses."""
    terms = query.casefold().split()
    results = []
    for ticket in tickets:
        if not terms and not requester:
            if tab == "CURRENT" and ticket.status not in CURRENT:
                continue
            if tab == "PAST" and ticket.status in CURRENT:
                continue
        if requester and requester.casefold() != ticket.requester.casefold():
            continue
        if priority in PRIORITIES and priority != ticket.priority:
            continue
        if terms:
            fields = [getattr(ticket, field) for field in SEARCH_FIELDS]
            fields.extend(entry["body"] for entry in repo.entries(ticket.number))
            fields.append(f"#{ticket.number}")
            haystack = "\n".join(fields).casefold()
            if any(term not in haystack for term in terms):
                continue
        results.append(ticket)
    ranks = {priority: rank for rank, priority in enumerate(reversed(PRIORITIES))}
    return sorted(results, key=lambda item: (
        ranks[item.priority] if priority_sort else 0,
        item.number if oldest else -item.number,
    ))


def overview(tickets: list[Ticket], today: date | None = None) -> str:
    """Summarize due follow-ups, stale tickets, and urgent current work."""
    today = today or date.today()
    active = [ticket for ticket in tickets if ticket.status in CURRENT]
    due = sum(bool(ticket.follow_up) and ticket.follow_up <= today.isoformat() for ticket in active)
    cutoff = (today - timedelta(days=3)).isoformat()
    stale = sum((ticket.updated[:10] or ticket.opened) <= cutoff for ticket in active)
    urgent = sum(ticket.priority == "Urgent" for ticket in active)
    parts = [f"{len(active)} current", f"{due} follow-ups due", f"{stale} no update in 3+ days"]
    if urgent:
        parts.append(f"{urgent} urgent")
    return " · ".join(parts)
