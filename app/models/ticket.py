"""Data and presentation rules for a support ticket."""
from dataclasses import asdict, dataclass
from datetime import date

CATEGORIES = ("Software", "Hardware", "Network", "Printer/Scanner",
              "Accounts/Access", "New Computer Setup", "Other")
PRIORITIES = {
    "Low": "Request or nice-to-have",
    "Normal": "Annoying but not blocking",
    "High": "Key task blocked or a deadline is near",
    "Urgent": "Someone can't work, or multiple people affected",
}
TRANSITIONS = {
    "Open": ("In Progress",),
    "In Progress": ("Waiting on User", "Resolved"),
    "Waiting on User": ("In Progress", "Resolved"),
    "Resolved": ("Closed",),
    "Closed": ("Open",),
}
CURRENT = tuple(TRANSITIONS)[:3]
REQUESTER_FIELDS = ("requester", "job", "email", "phone", "department")


@dataclass
class Ticket:
    """Store ISO dates and keep the issue title separate from its email subject."""
    title: str
    requester: str
    opened: str
    number: int = 0
    category: str = "Other"
    device: str = ""
    priority: str = "Normal"
    status: str = "Open"
    summary: str = ""
    sent: str = ""
    resolution: str = ""
    minutes: int | None = None
    resolved: str = ""
    follow_up: str = ""
    thread: str = ""
    related: tuple[int, ...] = ()
    job: str = ""
    email: str = ""
    phone: str = ""
    department: str = ""
    updated: str = ""
    sample: bool = False
    operating_system: str = ""

    @property
    def subject(self) -> str:
        """Return the full email subject."""
        return f"{self.title} [Ticket #{self.number} {date.fromisoformat(self.opened):%m-%d-%y}]"

    def payload(self) -> dict:
        """Return a serializable record without its database key."""
        record = asdict(self)
        del record["number"]
        return record
