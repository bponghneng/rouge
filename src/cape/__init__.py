"""Cape consolidated tooling package."""

from importlib import metadata

__all__ = ["cli", "core", "adw", "worker"]

try:
    __version__ = metadata.version("cape")
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
