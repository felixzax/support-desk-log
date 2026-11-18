"""Ticket editor and requester autocomplete widgets."""
from dataclasses import replace
from datetime import date
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.models.ticket import CATEGORIES, PRIORITIES, REQUESTER_FIELDS, TRANSITIONS, Ticket
from app.services.tickets import Tickets

PASSWORD_NOTE = "Don't store passwords here."


def priority_box(include_all: bool = False) -> QComboBox:
    """Create the priority selector with definitions on its options."""
    box = QComboBox()
    if include_all:
        box.addItem("All priorities")
    for priority, description in PRIORITIES.items():
        box.addItem(priority)
        box.setItemData(box.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
    box.currentIndexChanged.connect(
        lambda: box.setToolTip(PRIORITIES.get(box.currentText(), ""))
    )
    return box


class TicketEditor(QDialog):
    """Collect and validate a new ticket or an update to an existing one."""

    def __init__(self, service: Tickets, ticket: Ticket | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.service = service
        self.draft = ticket or Ticket("", "", date.today().isoformat())
        self.result_ticket: Ticket | None = None
        self.setWindowTitle("Edit ticket" if ticket else "New ticket")
        self.resize(620, 740)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        form = QFormLayout(content)
        form.setVerticalSpacing(8)
        self.fields = {}
        self.line(form, "title", "Issue title", "Printer Not Connecting")
        self.line(form, "requester", "Requester", "Jane Smith")
        self.line(form, "job", "Job title", "Office Manager")
        email = self.line(form, "email", "Email")
        copy = QPushButton("Copy Email")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(email.text()))
        form.removeWidget(email)
        row = QHBoxLayout()
        row.addWidget(email)
        row.addWidget(copy)
        form.setLayout(form.rowCount() - 1, QFormLayout.ItemRole.FieldRole, row)
        self.line(form, "phone", "Phone or extension")
        self.line(form, "department", "Department / location")

        self.category = QComboBox()
        self.category.addItems(CATEGORIES)
        self.category.setCurrentText(self.draft.category)
        form.addRow("Category", self.category)
        self.line(form, "device", "Device / software", "Office laser printer")
        os_field = self.line(form, "operating_system", "Operating system", "e.g. Windows 11 24H2")
        os_options = QCompleter(("Windows 11", "Windows 10", "Windows Server", "macOS", "Linux",
                                 "ChromeOS", "iOS", "Android"), os_field)
        os_options.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        os_field.setCompleter(os_options)
        self.priority = priority_box()
        self.priority.setCurrentText(self.draft.priority)
        form.addRow("Priority", self.priority)
        self.status = QComboBox()
        self.status.addItems(
            (self.draft.status, *TRANSITIONS[self.draft.status])
            if ticket else ("Open", "In Progress")
        )
        form.addRow("Status", self.status)
        self.line(form, "opened", "Date opened", "YYYY-MM-DD")
        self.line(form, "resolved", "Date resolved", "YYYY-MM-DD")
        self.line(form, "follow_up", "Follow-up date", "YYYY-MM-DD")
        minutes = self.line(form, "minutes", "Minutes spent")
        minutes.setValidator(QIntValidator(0, 2147483647, minutes))
        self.line(form, "thread", "Email thread link")
        for key, label in (("summary", "Problem summary"), ("sent", "What I sent"),
                           ("resolution", "Resolution summary")):
            note = QPlainTextEdit(getattr(self.draft, key))
            note.setFixedHeight(72)
            form.addRow(label, note)
            form.addRow("", QLabel(PASSWORD_NOTE))
            self.fields[key] = note

        known = service.repo.tickets()
        self.related = QListWidget()
        self.related.setFixedHeight(100)
        for other in known:
            if other.number != self.draft.number:
                item = QListWidgetItem(f"#{other.number} · {other.title}", self.related)
                item.setData(Qt.ItemDataRole.UserRole, other.number)
                item.setCheckState(Qt.CheckState.Checked if other.number in self.draft.related
                                   else Qt.CheckState.Unchecked)
        form.addRow("Related tickets", self.related)

        self.requesters = {}
        for other in sorted(known, key=lambda item: item.updated, reverse=True):
            self.requesters.setdefault(other.requester.casefold(), other)
        completer = QCompleter([item.requester for item in self.requesters.values()], self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.fields["requester"].setCompleter(completer)
        completer.activated[str].connect(self.fill_requester)
        self.status.currentTextChanged.connect(self.status_changed)
        self.status_changed(self.status.currentText())
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.save)
        self.fields["title"].setFocus()

    def line(self, form: QFormLayout, key: str, label: str, hint: str = "") -> QLineEdit:
        """Add an editable text field with an optional placeholder."""
        current = getattr(self.draft, key)
        widget = QLineEdit("" if current is None else str(current))
        widget.setPlaceholderText(hint)
        self.fields[key] = widget
        form.addRow(label, widget)
        return widget

    def fill_requester(self, name: str) -> None:
        """Fill contact details when the user selects a saved requester."""
        requester = self.requesters.get(name.casefold())
        if requester:
            for key in REQUESTER_FIELDS:
                self.fields[key].setText(getattr(requester, key))

    def status_changed(self, status: str) -> None:
        """Prompt for a resolution when resolving a ticket."""
        self.fields["resolution"].setPlaceholderText(
            "Required to mark this ticket Resolved" if status == "Resolved" else ""
        )
        self.fields["resolved"].setPlaceholderText(
            "Today if left blank" if status == "Resolved" else "YYYY-MM-DD"
        )

    def save(self) -> None:
        """Submit the editor to the ticket service."""
        values = {
            key: (widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()).strip()
            for key, widget in self.fields.items()
        }
        try:
            values["minutes"] = int(values["minutes"]) if values["minutes"] else None
            related = tuple(
                self.related.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(self.related.count())
                if self.related.item(index).checkState() == Qt.CheckState.Checked
            )
            self.result_ticket = self.service.save(replace(
                self.draft, **values, category=self.category.currentText(),
                priority=self.priority.currentText(), status=self.status.currentText(), related=related,
            ))
        except (ValueError, DatabaseError) as error:
            QMessageBox.warning(self, "Check ticket details", str(error))
            return
        self.accept()
