"""Hardware catalog validation, searches, and manual import/export."""
from dataclasses import replace
from pathlib import Path, PureWindowsPath

from app.data.hardware import HardwareRepository
from app.models.hardware import Hardware

MAX_MANUAL_BYTES = 25 * 1024 * 1024
MANUAL_SUFFIXES = {".pdf", ".docx", ".txt"}


def validate_hardware(item: Hardware) -> Hardware:
    """Normalize fields and require a type, make, and model."""
    values = {key: getattr(item, key) for key in ("kind", "make", "model", "power", "ink", "location")}
    if any(not isinstance(value, str) for value in values.values()):
        raise ValueError("Hardware fields must contain text.")
    values = {key: value.strip() for key, value in values.items()}
    if not (values["kind"] and values["make"] and values["model"]):
        raise ValueError("Enter the device type, make, and model.")
    return replace(item, **values)


def validate_manual(name: str, content: bytes) -> None:
    """Check filename, supported document type, and attachment size."""
    path = PureWindowsPath(name)
    if path.name != name or "/" in name or ":" in name or path.suffix.lower() not in MANUAL_SUFFIXES:
        raise ValueError("Select a PDF, DOCX, or TXT manual.")
    if not content or len(content) > MAX_MANUAL_BYTES:
        raise ValueError("Each manual must be between 1 byte and 25 MB.")


class Catalog:
    """Manage hardware independently from ticket tracking."""

    def __init__(self, storage: HardwareRepository) -> None:
        self.storage = storage

    def search(self, text: str) -> list[Hardware]:
        """Find models by type, make, model, cable, or cartridge."""
        terms = text.casefold().split()
        results = []
        for item in self.storage.items():
            fields = (item.kind, item.make, item.model, item.power, item.ink, item.location)
            haystack = " ".join(fields).casefold()
            if all(term in haystack for term in terms):
                results.append(item)
        return results

    def save(self, item: Hardware) -> int:
        """Save a valid catalog record."""
        return self.storage.save(validate_hardware(item))

    def attach(self, identifier: int, path: Path) -> None:
        """Import a bounded local copy of a manual."""
        with path.open("rb") as handle:
            content = handle.read(MAX_MANUAL_BYTES + 1)
        validate_manual(path.name, content)
        self.storage.add_manual(identifier, path.name, content)

    def save_copy(self, identifier: int, manual: int, path: Path) -> None:
        """Write the stored document to a user-selected location."""
        path.write_bytes(self.storage.read_manual(identifier, manual))
