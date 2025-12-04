"""Worker utilities for Cape TUI."""

from typing import Optional

# Worker options: (display_name, worker_id)
# Grouped by fleet: Alleycat, Nebuchadnezzar, Tydirium
WORKER_OPTIONS: list[tuple[str, str | None]] = [
    ("Unassigned", None),
    ("Alleycat 1 (alleycat-1)", "alleycat-1"),
    ("Alleycat 2 (alleycat-2)", "alleycat-2"),
    ("Alleycat 3 (alleycat-3)", "alleycat-3"),
    ("Nebuchadnezzar 1 (hailmary-1)", "hailmary-1"),
    ("Nebuchadnezzar 2 (hailmary-2)", "hailmary-2"),
    ("Nebuchadnezzar 3 (hailmary-3)", "hailmary-3"),
    ("Tydirium 1 (tydirium-1)", "tydirium-1"),
    ("Tydirium 2 (tydirium-2)", "tydirium-2"),
    ("Tydirium 3 (tydirium-3)", "tydirium-3"),
]

# Build lookup dictionary from worker_id to display name (without the worker_id suffix)
_WORKER_DISPLAY_NAMES: dict[str | None, str] = {}
for display_name, worker_id in WORKER_OPTIONS:
    if worker_id is None:
        _WORKER_DISPLAY_NAMES[None] = ""
    else:
        # Extract just the fleet name and number (e.g., "Alleycat 1" from "Alleycat 1 (alleycat-1)")
        name_part = display_name.split(" (")[0]
        _WORKER_DISPLAY_NAMES[worker_id] = name_part


def get_worker_display_name(worker_id: Optional[str]) -> str:
    """Get the display name for a worker ID.

    Args:
        worker_id: The worker ID (e.g., "alleycat-1", "hailmary-2") or None for unassigned.

    Returns:
        The display name (e.g., "Alleycat 1", "Nebuchadnezzar 2") or empty string for unassigned.
    """
    return _WORKER_DISPLAY_NAMES.get(worker_id, "")
