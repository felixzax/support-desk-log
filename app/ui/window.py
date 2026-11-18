"""Main ticket browser and detail panel."""
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter, QTabBar, QTabWidget,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QInputDialog,
)

from app.data.hardware import HardwareRepository
from app.models.ticket import CURRENT, TRANSITIONS, Ticket
from app.services.backup import Archive
from app.services.hardware import Catalog
from app.services.search import browse, overview
from app.services.tickets import Tickets
from app.ui.forms import PASSWORD_NOTE, TicketEditor, priority_box
from app.ui.style import apply_theme

STATUS_COLORS = {
    "Open": "#4085e7", "In Progress": "#7a70dc", "Waiting on User": "#d78e27",
    "Resolved": "#359b76", "Closed": "#8590a0",
}
ROLE = Qt.ItemDataRole.UserRole


def plain(content: str, name: str = "") -> QLabel:
    """Display user-entered text literally."""
    label = QLabel(content)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def action(text: str, callback: Callable[[], object], primary: bool = False) -> QPushButton:
    """Create a labeled action button."""
    button = QPushButton(text)
    if primary:
        button.setObjectName("primary")
    button.clicked.connect(lambda: callback())
    return button


class MainWindow(QMainWindow):
    """Browse tickets, route actions to services, and show their results."""

    def __init__(self, service: Tickets, archive: Archive) -> None:
        super().__init__()
        self.service = service
        self.archive = archive
        self.requester_filter = ""
        self.dark = service.repo.setting("theme") == "dark"
        self.setWindowTitle("Support Desk Log")
        self.resize(1320, 820)
        self.setMinimumSize(890, 530)

        from app.ui.hardware import HardwarePage

        self.sections = QTabWidget()
        self.setCentralWidget(self.sections)
        central = QWidget()
        self.sections.addTab(central, "Tickets")
        self.hardware = HardwarePage(Catalog(HardwareRepository(service.repo)))
        self.sections.addTab(self.hardware, "Hardware")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(plain("Support Desk Log", "brand"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tickets and progress logs")
        self.search.setAccessibleName("Search tickets")
        self.search.setClearButtonEnabled(True)
        top.addWidget(self.search, 1)
        top.addWidget(action("+ New Ticket", self.edit, True))
        self.theme = action("Light mode" if self.dark else "Dark mode", self.toggle_theme)
        top.addWidget(self.theme)
        settings = action("⚙", self.settings)
        settings.setToolTip("Settings")
        settings.setAccessibleName("Settings")
        top.addWidget(settings)
        layout.addLayout(top)
        self.summary = plain("", "muted")
        layout.addWidget(self.summary)

        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        options = QHBoxLayout()
        self.tabs = QTabBar()
        for tab in ("CURRENT", "PAST", "ALL"):
            self.tabs.addTab(tab)
        options.addWidget(self.tabs)
        self.priority = priority_box(True)
        options.addWidget(self.priority)
        options.addStretch()
        left_layout.addLayout(options)
        sort_row = QHBoxLayout()
        self.sort = QComboBox()
        self.sort.addItems(("By ticket number", "By priority, then ticket number"))
        sort_row.addWidget(self.sort)
        self.oldest = QCheckBox("Oldest first")
        sort_row.addWidget(self.oldest)
        sort_row.addStretch()
        left_layout.addLayout(sort_row)
        self.requester_button = action("", self.clear_requester)
        self.requester_button.hide()
        left_layout.addWidget(self.requester_button)

        self.list = QTreeWidget()
        self.list.setHeaderLabels(("", "Ticket", "Issue", "Requester", "Updated", "Priority"))
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setColumnWidth(0, 23)
        self.list.setColumnWidth(1, 55)
        self.list.setColumnWidth(2, 175)
        self.list.setColumnWidth(3, 118)
        self.list.setColumnWidth(4, 95)
        left_layout.addWidget(self.list)
        splitter.addWidget(left)

        self.detail = QScrollArea()
        self.detail.setWidgetResizable(True)
        splitter.addWidget(self.detail)
        splitter.setSizes((610, 680))
        splitter.setChildrenCollapsible(False)
        for signal in (self.search.textChanged, self.tabs.currentChanged,
                       self.priority.currentIndexChanged, self.sort.currentIndexChanged,
                       self.oldest.toggled):
            signal.connect(lambda *_: self.refresh())
        self.list.itemSelectionChanged.connect(self.show_detail)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.edit)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.focus_search)
        apply_theme(QApplication.instance(), self.dark)
        self.refresh()

    def refresh(self, select: int | None = None) -> None:
        """Requery the list and preserve the selected ticket when possible."""
        current = self.list.currentItem()
        selected = select or (current.data(1, ROLE) if current else None)
        query = self.search.text().strip()
        tab = self.tabs.tabText(self.tabs.currentIndex())
        tickets = self.service.repo.tickets()
        self.sort.setEnabled(tab == "CURRENT" and not query and not self.requester_filter)
        visible = browse(
            self.service.repo, tickets, tab=tab, query=query, requester=self.requester_filter,
            priority=self.priority.currentText(), oldest=self.oldest.isChecked(),
            priority_sort=self.sort.isEnabled() and self.sort.currentIndex() == 1,
        )
        self.summary.setText(overview(tickets))
        self.list.blockSignals(True)
        self.list.clear()
        for ticket in visible:
            item = QTreeWidgetItem(self.list, (
                "●", f"#{ticket.number}", ticket.title, ticket.requester,
                ticket.updated[:10], ticket.priority if ticket.priority in ("High", "Urgent") else "",
            ))
            item.setData(1, ROLE, ticket.number)
            item.setToolTip(0, ticket.status)
            item.setForeground(0, QColor(STATUS_COLORS[ticket.status]))
            if ticket.priority in ("High", "Urgent"):
                item.setForeground(5, QColor("#e18a32" if ticket.priority == "High" else "#db565c"))
            if ticket.number == selected:
                self.list.setCurrentItem(item)
        if select and self.list.currentItem() is None and tab != "ALL":
            if any(ticket.number == select for ticket in tickets):
                self.list.blockSignals(False)
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(2)
                self.tabs.blockSignals(False)
                self.refresh(select)
                return
        self.list.blockSignals(False)
        self.show_detail()

    def show_detail(self) -> None:
        """Render the selected ticket in reading order."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(8)
        self.detail.setWidget(content)
        item = self.list.currentItem()
        if item is None:
            message = ("No tickets yet. Press Ctrl+N to add your first."
                       if not self.service.repo.tickets() else
                       "Select a ticket." if self.list.topLevelItemCount() else "No matching tickets.")
            layout.addStretch()
            label = plain(message, "muted")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            layout.addStretch()
            return
        ticket = self.service.repo.get(item.data(1, ROLE))
        layout.addWidget(plain(ticket.subject, "heading"))
        layout.addWidget(plain(f"{ticket.status} · {ticket.priority} priority", "muted"))
        requester = " · ".join(filter(None, (ticket.requester, ticket.job, ticket.department)))
        layout.addWidget(action(requester, lambda: self.filter_requester(ticket.requester)),
                         0, Qt.AlignmentFlag.AlignLeft)
        buttons = QHBoxLayout()
        buttons.addWidget(action("Copy Title", lambda: QApplication.clipboard().setText(ticket.subject)))
        if ticket.email:
            buttons.addWidget(action("Copy Email", lambda: QApplication.clipboard().setText(ticket.email)))
        buttons.addWidget(action("Edit" if ticket.status in CURRENT else "Edit details", lambda: self.edit(ticket)))
        for target in TRANSITIONS[ticket.status]:
            label = {"Open": "Reopen", "Closed": "Close ticket", "Resolved": "Resolve"}.get(target, target)
            buttons.addWidget(action(label, lambda checked=False, status=target: self.transition(ticket, status)))
        buttons.addStretch()
        layout.addLayout(buttons)
        details = [f"{ticket.category} · Opened {ticket.opened}"]
        for caption, value in (
            ("Device / software", ticket.device), ("Operating system", ticket.operating_system),
            ("Resolved", ticket.resolved),
            ("Follow-up", ticket.follow_up), ("Minutes spent", ticket.minutes),
            ("Email", ticket.email), ("Phone", ticket.phone), ("Email thread link", ticket.thread),
        ):
            if value is not None and value != "":
                details.append(f"{caption} · {value}")
        if ticket.summary:
            details.extend(("", ticket.summary))
        if ticket.resolution:
            details.extend(("", f"Resolution · {ticket.resolution}"))
        section = QVBoxLayout()
        section.addWidget(plain("\n".join(details)))
        section.addWidget(plain(PASSWORD_NOTE, "muted"))
        for number in ticket.related:
            related = self.service.repo.get(number)
            section.addWidget(action(f"#{number} · {related.title}",
                                     lambda checked=False, n=number: self.open_related(n)),
                              0, Qt.AlignmentFlag.AlignLeft)
        self.section(layout, "Details", section)
        sent = QVBoxLayout()
        sent.addWidget(plain(ticket.sent or "No sent instructions recorded.", "" if ticket.sent else "muted"))
        sent.addWidget(plain(PASSWORD_NOTE, "muted"))
        self.section(layout, "What I sent", sent)
        self.timeline(layout, ticket)
        layout.addStretch()
        layout.addWidget(action("Delete ticket", lambda: self.delete(ticket)), 0, Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def section(parent: QVBoxLayout, title: str, layout: QVBoxLayout) -> None:
        """Add a collapsible section that starts expanded."""
        toggle = QToolButton()
        toggle.setText(title)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.DownArrow)
        toggle.setCheckable(True)
        toggle.setChecked(True)
        content = QWidget()
        content.setLayout(layout)
        layout.setContentsMargins(8, 0, 0, 4)
        toggle.toggled.connect(content.setVisible)
        toggle.toggled.connect(lambda expanded: toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        ))
        parent.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
        parent.addWidget(content)

    def timeline(self, layout: QVBoxLayout, ticket: Ticket) -> None:
        """Show audit events and editable manual notes in the same timeline."""
        log = QVBoxLayout()
        row = QHBoxLayout()
        note = QLineEdit()
        note.setPlaceholderText("Emailed setup steps")
        note.setAccessibleName("Progress log entry")
        row.addWidget(note, 1)
        row.addWidget(action("Add", lambda: self.save_note(ticket, note.text()), True))
        note.returnPressed.connect(lambda: self.save_note(ticket, note.text()))
        log.addLayout(row)
        log.addWidget(plain(PASSWORD_NOTE, "muted"))
        for entry in self.service.repo.entries(ticket.number):
            date = datetime.fromisoformat(entry["timestamp"]).astimezone()
            caption = f"{date:%b %d, %Y · %H:%M} · {entry['kind']}"
            log.addWidget(plain(caption, "muted"))
            log.addWidget(plain(entry["body"], "" if entry["kind"] == "Note" else "muted"))
            if entry["kind"] == "Note":
                row = QHBoxLayout()
                row.addWidget(action("Edit note", lambda checked=False, e=entry: self.edit_note(ticket, e)))
                row.addWidget(action("Delete note", lambda checked=False, e=entry: self.delete_note(ticket, e)))
                row.addStretch()
                log.addLayout(row)
        self.section(layout, "Progress log", log)

    def focus_search(self) -> None:
        """Focus search in the current section."""
        search = self.hardware.query if self.sections.currentWidget() is self.hardware else self.search
        search.setFocus()

    def edit(self, ticket: Ticket | None = None) -> None:
        """Open the editor and select its result."""
        self.sections.setCurrentIndex(0)
        editor = TicketEditor(self.service, ticket, self)
        if editor.exec() == QDialog.DialogCode.Accepted and editor.result_ticket:
            self.refresh(editor.result_ticket.number)

    def transition(self, ticket: Ticket, status: str) -> None:
        """Prompt for resolution details when the workflow reaches Resolved."""
        if status == "Resolved":
            editor = TicketEditor(self.service, ticket, self)
            editor.status.setCurrentText(status)
            editor.fields["resolution"].setFocus()
            if editor.exec() == QDialog.DialogCode.Accepted:
                self.refresh(ticket.number)
            return
        self.perform(lambda: self.service.save(replace(ticket, status=status)), ticket.number)

    def perform(self, callback: Callable[[], object], select: int | None = None) -> None:
        """Show operation errors in a dialog and refresh successful changes."""
        try:
            callback()
        except (ValueError, OSError, DatabaseError) as error:
            QMessageBox.warning(self, "Support Desk Log", str(error))
        else:
            self.refresh(select)

    def save_note(self, ticket: Ticket, text: str, entry: int | None = None) -> None:
        self.perform(lambda: self.service.note(ticket.number, text, entry), ticket.number)

    def edit_note(self, ticket: Ticket, entry: dict) -> None:
        text, accepted = QInputDialog.getText(self, "Edit note", PASSWORD_NOTE, text=entry["body"])
        if accepted:
            self.save_note(ticket, text, entry["id"])

    def delete_note(self, ticket: Ticket, entry: dict) -> None:
        if QMessageBox.question(self, "Delete note", "Delete this progress log entry?") == QMessageBox.StandardButton.Yes:
            self.perform(lambda: self.service.note(ticket.number, None, entry["id"]), ticket.number)

    def delete(self, ticket: Ticket) -> None:
        if QMessageBox.question(self, "Delete ticket", f"Permanently delete ticket #{ticket.number}?") == QMessageBox.StandardButton.Yes:
            self.perform(lambda: self.service.delete(ticket.number))

    def filter_requester(self, requester: str) -> None:
        self.requester_filter = requester
        self.requester_button.setText(f"{requester} · Clear filter")
        self.requester_button.show()
        self.search.clear()
        self.priority.setCurrentIndex(0)
        self.tabs.setCurrentIndex(2)
        self.refresh()

    def clear_requester(self) -> None:
        self.requester_filter = ""
        self.requester_button.hide()
        self.refresh()

    def open_related(self, number: int) -> None:
        self.clear_requester()
        self.search.clear()
        self.priority.setCurrentIndex(0)
        self.tabs.setCurrentIndex(2)
        self.refresh(number)

    def toggle_theme(self) -> None:
        self.dark = not self.dark
        self.service.repo.set_setting("theme", "dark" if self.dark else "light")
        self.theme.setText("Light mode" if self.dark else "Dark mode")
        apply_theme(QApplication.instance(), self.dark)

    def settings(self) -> None:
        from app.ui.settings import Settings
        Settings(self.service, self.archive, self).exec()
        self.hardware.refresh()
        self.dark = self.service.repo.setting("theme") == "dark"
        self.theme.setText("Light mode" if self.dark else "Dark mode")
        apply_theme(QApplication.instance(), self.dark)
        self.refresh()

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.archive.backup()
        except (ValueError, OSError, DatabaseError) as error:
            answer = QMessageBox.question(self, "Backup failed", f"{error}\n\nClose anyway?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
