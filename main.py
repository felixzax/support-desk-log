"""Launch Support Desk Log with data in the user's local application folder."""
import sys
from sqlite3 import Error as DatabaseError

from PySide6.QtWidgets import QApplication, QMessageBox

from app.data.database import connect, data_dir
from app.data.repository import Repository
from app.services.backup import Archive
from app.services.tickets import Tickets
from app.ui.window import MainWindow
from app.version import VERSION


def main() -> int:
    """Open the database before showing the desktop window."""
    app = QApplication(sys.argv)
    app.setApplicationName("Support Desk Log")
    app.setApplicationVersion(VERSION)
    folder = data_dir()
    try:
        db = connect(folder / "tickets.sqlite3")
    except (ValueError, OSError, DatabaseError) as error:
        QMessageBox.critical(None, "Cannot open Support Desk Log", str(error))
        return 1
    try:
        repo = Repository(db)
        window = MainWindow(Tickets(repo), Archive(repo, folder / "backups"))
        window.show()
        return app.exec()
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
