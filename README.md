# Support Desk Log

An offline Windows 11 desktop application for logging IT support tickets and the instructions you send from your own email client.

## Features

- Sequential ticket numbers, copyable email subject lines, and an optional operating system field
- Current, past, and all-ticket views with priority filters, requester history, and full-text search
- Timestamped progress notes and automatic status and priority history
- Requester autocomplete, related tickets, and follow-up dates
- Excel and CSV export, monthly summaries, and automatic JSON backups
- Searchable hardware catalog with power cable, ink and toner details, and offline manuals
- Light and dark themes and optional fictional sample tickets

## Screenshots

_Screenshot placeholders for the empty ticket browser and ticket detail with progress log._

## Run from source on Windows 11

1. Install Python 3.12 with the Windows Python launcher.
2. Clone this repository and open Command Prompt in the project folder.
3. Create the environment, install dependencies, and launch:

   ```bat
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe main.py
   ```

Use **Ctrl+N** for a new ticket, **Ctrl+F** for search, **Ctrl+Enter** to save the ticket editor, and **Esc** to close a dialog. Press **Enter** in the progress log field to add your note.

## Package the Windows executable

1. Run `build.bat` from the project folder on Windows 11.
2. The script installs dependencies, runs pytest, and builds `dist\Support Desk Log.exe`.
3. Open the executable directly. The destination machine does not need Python.

The first installation and packaging step downloads dependencies. The application runs offline after installation.

## Hardware and manuals

Open **Hardware** and select **Add Hardware** to record a device type, make, model,
location, power cable or adapter, and ink or toner. Select a record to attach PDF, DOCX, or TXT manuals
up to 25 MB per file. The app stores its own copy. Use **Save a copy** to retrieve a manual.

Version 1.1 backups contain hardware and manuals. Restoring a version 1.0 backup replaces
ticket data and settings while preserving the hardware catalog.

## Local data and reports

SQLite data lives in `%APPDATA%\Support Desk Log\tickets.sqlite3`. JSON copies are kept in the adjacent `backups` folder. Settings includes manual backup and restore. Restore replaces local records and makes a backup of the current data first. The next ticket number stays at or above the counter already reached.

Exports filter on the date opened, with both endpoints included. The monthly summary counts openings by date opened and resolutions by date resolved, and ranks categories by tickets opened during that month. Reopening a closed ticket clears its resolved date while retaining the event history.

## Development

The stack is Python 3.12, PySide6, SQLite, openpyxl, pytest, and PyInstaller. Application layers live under `app/ui`, `app/services`, `app/data`, and `app/models`. Run tests with `python -m pytest -q` from the repository root.
