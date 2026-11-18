"""CSV, Excel and monthly reporting for local ticket records."""
import csv
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean

from openpyxl import Workbook

from app.models.ticket import Ticket

HEADERS = ("Ticket number", "Title", "Requester", "Job title", "Department", "Category",
           "Device / software", "Priority", "Status", "Date opened", "Date resolved", "Minutes spent",
           "Operating system")


def export(tickets: list[Ticket], path: Path, start: date | None = None,
           end: date | None = None) -> int:
    """Export the inclusive date-opened range, preserving user text as text."""
    if start and end and start > end:
        raise ValueError("The start date must be on or before the end date.")
    rows = []
    for ticket in tickets:
        opened = date.fromisoformat(ticket.opened)
        if (start and opened < start) or (end and opened > end):
            continue
        rows.append((ticket.number, ticket.title, ticket.requester, ticket.job, ticket.department,
                     ticket.category, ticket.device, ticket.priority, ticket.status, ticket.opened,
                     ticket.resolved, ticket.minutes, ticket.operating_system))
    if path.suffix.lower() == ".xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Tickets"
        for row in (HEADERS, *rows):
            sheet.append(row)
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(
                55, max(14, max(len(str(cell.value or "")) for cell in column) + 2)
            )
        workbook.save(path)
    elif path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADERS)
            for row in rows:
                writer.writerow([csv_value(value) for value in row])
    else:
        raise ValueError("Choose a .xlsx or .csv filename.")
    return len(rows)


def csv_value(value: object) -> object:
    """Keep spreadsheet applications from evaluating ticket text as formulas."""
    if isinstance(value, str) and (value.startswith(("\t", "\r", "\n"))
                                   or value.lstrip().startswith(("=", "+", "-", "@"))):
        return "'" + value
    return value


def monthly(tickets: list[Ticket], month: date) -> str:
    """Count openings and resolutions independently within the selected month."""
    prefix = month.strftime("%Y-%m")
    opened = [ticket for ticket in tickets if ticket.opened.startswith(prefix)]
    resolved = [ticket for ticket in tickets if ticket.resolved.startswith(prefix)]
    days = [(date.fromisoformat(ticket.resolved) - date.fromisoformat(ticket.opened)).days
            for ticket in resolved]
    categories = Counter(ticket.category for ticket in opened)
    top = ", ".join(f"{name} ({count})" for name, count in categories.most_common(3)) or "—"
    average = f"{mean(days):.1f}" if days else "—"
    return (f"{month:%B %Y}\nTickets opened · {len(opened)}\nTickets resolved · {len(resolved)}\n"
            f"Average days to resolve · {average}\nTop categories opened · {top}")
