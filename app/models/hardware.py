"""Hardware catalog records."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Hardware:
    """Describe the supplies and power connections for a device model."""

    kind: str
    make: str
    model: str
    power: str = ""
    ink: str = ""
    id: int | None = None
    location: str = ""
