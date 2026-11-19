"""Settings, reporting, export and backup dialogs."""
from collections.abc import Callable
from datetime import date
from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from app.services.backup import Archive
from app.services.export import export, monthly
from app.services.tickets import Tickets
from app.ui.window import action, plain
from app.version import VERSION


class Settings(QDialog):
    """Expose local preferences, reports, and data maintenance."""

    def __init__(self, service: Tickets, archive: Archive, parent: QWidget) -> None:
        super().__init__(parent)
        self.service = service
        self.archive = archive
        self.setWindowTitle("Settings")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        general = QWidget()
        general_form = QFormLayout(general)
        self.number = QSpinBox()
        self.number.setRange(1, 2147483647)
        self.number.setValue(int(service.repo.setting("starting_number")))
        general_form.addRow("Starting ticket number", self.number)
        general_form.addRow(action("Save starting number", self.starting_number))
        self.next_ticket = plain("", "muted")
        general_form.addRow(self.next_ticket)
        general_form.addRow(action("Load sample data", lambda: self.run(service.load_samples)))
        general_form.addRow(action("Clear sample data", self.clear_samples))
        tabs.addTab(general, "General")

        backups = QWidget()
        backup_layout = QVBoxLayout(backups)
        backup_layout.addWidget(plain("A JSON backup is saved on close. The latest 10 are kept."))
        backup_layout.addWidget(plain(str(archive.directory), "muted"))
        backup_layout.addWidget(action("Backup now", self.backup))
        backup_layout.addWidget(plain(
            "To move to a new computer, export a backup here, copy the file, "
            "then import it on the new computer."
        ))
        backup_layout.addWidget(action("Export backup…", self.export_backup))
        backup_layout.addWidget(action("Import backup…", self.restore))
        backup_layout.addStretch()
        tabs.addTab(backups, "Backup")

        report = QWidget()
        report_form = QFormLayout(report)
        self.start = QLineEdit()
        self.end = QLineEdit()
        for field in (self.start, self.end):
            field.setPlaceholderText("YYYY-MM-DD (optional)")
        report_form.addRow(plain("Export tickets by date opened. Leave both dates blank to export all."))
        report_form.addRow("From", self.start)
        report_form.addRow("Through", self.end)
        report_form.addRow(action("Export tickets…", self.export))
        self.month = QLineEdit(date.today().strftime("%Y-%m"))
        self.month.setPlaceholderText("YYYY-MM")
        report_form.addRow("Summary month", self.month)
        self.summary = plain("")
        report_form.addRow(self.summary)
        self.month.textChanged.connect(self.update_summary)
        self.update_summary()
        report_form.addRow(action("Copy summary", self.copy_summary))
        tabs.addTab(report, "Export & summary")

        about = QWidget()
        about_layout = QVBoxLayout(about)
        about_layout.addWidget(plain("Support Desk Log", "heading"))
        about_layout.addWidget(QLabel(f"Version {VERSION}"))
        about_layout.addWidget(plain("Offline ticket tracking for desktop support."))
        about_layout.addStretch()
        tabs.addTab(about, "About")
        layout.addWidget(action("Done", self.accept))

    def run(self, callback: Callable[[], object], success: str = "") -> None:
        """Report failures without leaving the settings dialog."""
        try:
            result = callback()
        except (ValueError, OSError, DatabaseError) as error:
            QMessageBox.warning(self, "Support Desk Log", str(error))
        else:
            self.update_summary()
            if success:
                QMessageBox.information(self, "Support Desk Log", success.format(result))

    def starting_number(self) -> None:
        self.run(lambda: self.service.starting_number(self.number.value()), "Starting number saved.")

    def clear_samples(self) -> None:
        if QMessageBox.question(self, "Clear sample data", "Delete the sample tickets and their logs?") == QMessageBox.StandardButton.Yes:
            self.run(self.service.clear_samples)

    def backup(self) -> None:
        self.run(self.archive.backup, "Backup saved to\n{}")

    def export_backup(self) -> None:
        """Save a full backup to a folder or removable drive chosen by the user."""
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        suggested = Path(documents) / self.archive.suggested_name()
        selected, _ = QFileDialog.getSaveFileName(
            self, "Export backup", str(suggested), "Support Desk Log backup (*.json)"
        )
        if selected:
            path = Path(selected)
            if not path.suffix:
                path = path.with_suffix(".json")
            self.run(lambda: self.archive.export(path), "Backup exported to\n{}")

    def restore(self) -> None:
        """Import either a portable or an automatic backup."""
        selected, _ = QFileDialog.getOpenFileName(
            self, "Import backup", str(self.archive.directory), "Support Desk Log backup (*.json)"
        )
        if selected and QMessageBox.question(
            self, "Import backup",
            "Import this backup? It replaces the local data it contains. A backup of the "
            "current data will be saved first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            def restore_archive() -> None:
                self.archive.restore(Path(selected))
                self.accept()

            self.run(restore_archive, "Backup imported.")

    def export(self) -> None:
        selected, file_type = QFileDialog.getSaveFileName(
            self, "Export tickets", "support-desk-tickets", "Excel workbook (*.xlsx);;CSV (*.csv)"
        )
        if not selected:
            return
        path = Path(selected)
        if not path.suffix:
            path = path.with_suffix(".xlsx" if file_type.startswith("Excel") else ".csv")
        self.run(lambda: export(
            self.service.repo.tickets(), path,
            date.fromisoformat(self.start.text().strip()) if self.start.text().strip() else None,
            date.fromisoformat(self.end.text().strip()) if self.end.text().strip() else None,
        ), "Exported {} ticket(s).")

    def update_summary(self) -> None:
        try:
            text = monthly(self.service.repo.tickets(), date.fromisoformat(f"{self.month.text().strip()}-01"))
        except ValueError:
            text = "Enter a month as YYYY-MM."
        self.summary.setText(text)
        self.next_ticket.setText(f"Next ticket · #{self.service.repo.setting('next_number')}")

    def copy_summary(self) -> None:
        try:
            month = date.fromisoformat(f"{self.month.text().strip()}-01")
        except ValueError:
            return
        QApplication.clipboard().setText(monthly(self.service.repo.tickets(), month))
