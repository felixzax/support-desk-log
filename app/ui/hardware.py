"""Searchable hardware catalog and document attachments."""
from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.models.hardware import Hardware
from app.services.hardware import Catalog
from app.ui.window import action, plain

ROLE = Qt.ItemDataRole.UserRole
DOCUMENT_FILTER = "Manuals (*.pdf *.docx *.txt)"


class HardwarePage(QWidget):
    """Browse, edit, and attach manuals to equipment models."""

    def __init__(self, catalog: Catalog) -> None:
        super().__init__()
        self.catalog = catalog
        self.items: dict[int, Hardware] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        bar = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search make, model, power cable, or ink")
        self.query.setAccessibleName("Search hardware")
        self.query.setClearButtonEnabled(True)
        bar.addWidget(self.query, 1)
        bar.addWidget(action("+ Add Hardware", self.edit, True))
        layout.addLayout(bar)
        self.records = QTreeWidget()
        self.records.setRootIsDecorated(False)
        self.records.setHeaderLabels(("Type", "Make", "Model", "Power cable / adapter", "Ink / toner"))
        for column, width in enumerate((140, 155, 185, 230)):
            self.records.setColumnWidth(column, width)
        layout.addWidget(self.records, 3)
        self.summary = plain("", "muted")
        layout.addWidget(self.summary)
        toolbar = QHBoxLayout()
        toolbar.addWidget(plain("Manuals", "brand"))
        toolbar.addStretch()
        self.edit_button = action("Edit hardware", self.edit_selected)
        self.delete_button = action("Delete hardware", self.delete_item)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.delete_button)
        layout.addLayout(toolbar)
        self.manuals = QListWidget()
        layout.addWidget(self.manuals, 2)
        self.hint = plain("", "muted")
        layout.addWidget(self.hint)
        manual_actions = QHBoxLayout()
        self.attach_button = action("Attach manuals…", self.attach)
        self.save_button = action("Save a copy…", self.save_copy)
        self.remove_button = action("Remove manual", self.remove_manual)
        for button in (self.attach_button, self.save_button, self.remove_button):
            manual_actions.addWidget(button)
        manual_actions.addStretch()
        layout.addLayout(manual_actions)
        self.query.textChanged.connect(lambda: self.refresh())
        self.records.currentItemChanged.connect(lambda: self.refresh_manuals())
        self.records.itemDoubleClicked.connect(lambda: self.edit_selected())
        self.manuals.currentItemChanged.connect(lambda: self.update_buttons())
        self.manuals.itemDoubleClicked.connect(lambda: self.save_copy())
        self.refresh()

    def selection(self) -> int | None:
        """Return the selected model ID."""
        row = self.records.currentItem()
        return row.data(0, ROLE) if row else None

    def refresh(self, identifier: int | None = None) -> None:
        """Refresh hardware records while retaining the selection."""
        identifier = identifier if identifier is not None else self.selection()
        self.records.blockSignals(True)
        self.records.clear()
        results = self.catalog.search(self.query.text())
        self.items = {item.id: item for item in results}
        for item in results:
            row = QTreeWidgetItem(self.records, (item.kind, item.make, item.model, item.power, item.ink))
            row.setData(0, ROLE, item.id)
            if item.id == identifier:
                self.records.setCurrentItem(row)
        self.records.blockSignals(False)
        self.summary.setText(f"{len(results)} hardware record(s)" if results else (
            "No matching hardware." if self.query.text().strip() else
            "No hardware yet. Select Add Hardware to get started."
        ))
        self.refresh_manuals()

    def refresh_manuals(self) -> None:
        """Refresh attachment names for the selected hardware record."""
        self.manuals.clear()
        identifier = self.selection()
        if identifier is not None:
            for manual, name, size in self.catalog.storage.manuals(identifier):
                row = QListWidgetItem(f"{name}  ·  {max(1, (size + 1023) // 1024):,} KB", self.manuals)
                row.setData(ROLE, (manual, name))
        self.hint.setText(
            "Select hardware to see its manuals." if identifier is None else
            "Attach PDF, DOCX, or TXT files up to 25 MB each." if not self.manuals.count() else ""
        )
        self.update_buttons()

    def update_buttons(self) -> None:
        """Enable actions according to the current selection."""
        for button in (self.edit_button, self.delete_button, self.attach_button):
            button.setEnabled(self.selection() is not None)
        for button in (self.save_button, self.remove_button):
            button.setEnabled(self.manuals.currentItem() is not None)

    def warn(self, error: Exception) -> None:
        """Display operation errors without discarding the current form."""
        QMessageBox.warning(self, "Hardware", str(error))

    def edit_selected(self) -> None:
        """Edit the current catalog entry."""
        item = self.items.get(self.selection())
        if item:
            self.edit(item)

    def edit(self, item: Hardware | None = None) -> None:
        """Open a short add/edit form for model details."""
        draft = item or Hardware("Computer", "", "")
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit hardware" if item else "Add hardware")
        dialog.setMinimumWidth(460)
        form = QFormLayout(dialog)
        kind = QComboBox()
        kind.setEditable(True)
        kind.addItems(("Computer", "Printer", "Monitor", "Scanner", "Dock", "Network equipment", "Other"))
        kind.setCurrentText(draft.kind)
        form.addRow("Device type", kind)
        make = QLineEdit(draft.make)
        model = QLineEdit(draft.model)
        power = QLineEdit(draft.power)
        power.setPlaceholderText("e.g. IEC C13 or 65 W USB-C")
        ink = QLineEdit(draft.ink)
        ink.setPlaceholderText("Cartridge or toner number, if applicable")
        for label, field in (("Make", make), ("Model", model),
                             ("Power cable / adapter", power), ("Ink / toner", ink)):
            form.addRow(label, field)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(buttons)

        def submit() -> None:
            try:
                identifier = self.catalog.save(Hardware(
                    kind.currentText(), make.text(), model.text(), power.text(), ink.text(), draft.id
                ))
            except (ValueError, DatabaseError) as error:
                self.warn(error)
                return
            dialog.accept()
            self.query.clear()
            self.refresh(identifier)

        buttons.accepted.connect(submit)
        buttons.rejected.connect(dialog.reject)
        QShortcut(QKeySequence("Ctrl+Return"), dialog, activated=submit)
        make.setFocus()
        dialog.exec()

    def delete_item(self) -> None:
        """Confirm deletion of a record and its attached manuals."""
        identifier = self.selection()
        if identifier is None or QMessageBox.question(
            self, "Delete hardware", "Delete this hardware record and its stored manuals?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.catalog.storage.delete(identifier)
        except DatabaseError as error:
            self.warn(error)
        self.refresh()

    def attach(self) -> None:
        """Import independent copies of the selected manual files."""
        identifier = self.selection()
        if identifier is None:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Attach manuals", "", DOCUMENT_FILTER)
        for file in files:
            try:
                self.catalog.attach(identifier, Path(file))
            except (OSError, ValueError, DatabaseError) as error:
                self.warn(ValueError(f"{Path(file).name}: {error}"))
        self.refresh_manuals()

    def save_copy(self) -> None:
        """Save a stored manual to a location the user chooses."""
        identifier, row = self.selection(), self.manuals.currentItem()
        if identifier is None or row is None:
            return
        manual, name = row.data(ROLE)
        file, _ = QFileDialog.getSaveFileName(self, "Save a copy of the manual", name)
        if file:
            try:
                self.catalog.save_copy(identifier, manual, Path(file))
            except (OSError, ValueError, DatabaseError) as error:
                self.warn(error)

    def remove_manual(self) -> None:
        """Confirm before removing the stored copy of a manual."""
        identifier, row = self.selection(), self.manuals.currentItem()
        if identifier is None or row is None:
            return
        manual, name = row.data(ROLE)
        if QMessageBox.question(
            self, "Remove manual", f"Remove the stored copy of {name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            try:
                self.catalog.storage.delete_manual(identifier, manual)
            except DatabaseError as error:
                self.warn(error)
            self.refresh_manuals()
