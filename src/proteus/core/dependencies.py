"""External-tool discovery.

find_tool() probes for a binary via, in order: an env var override, then
shutil.which(), then a hand-maintained list of known Windows install
locations. The known-location fallback exists because installers don't
reliably put themselves on PATH — confirmed directly this session for
both LibreOffice (never added itself) and Pandoc (only after manually
locating AppData\\Local\\Pandoc). Every converter that shells out to an
external tool uses this instead of a bare shutil.which() call, so
is_available() and the actual subprocess invocation always agree.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AvailabilityStatus:
    available: bool
    path: Path | None
    source: str  # "env" | "path" | "known-location" | "not-found"


# Hand-maintained, deliberately — matches the project's existing
# no-plugin-scanning registry convention. Extend this when a new external
# tool's installer turns out not to add itself to PATH either.
KNOWN_INSTALL_PATHS: dict[str, tuple[Path, ...]] = {
    "soffice": (
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ),
    "pandoc": (
        Path.home() / "AppData" / "Local" / "Pandoc" / "pandoc.exe",
        Path(r"C:\Program Files\Pandoc\pandoc.exe"),
    ),
}


def find_tool(bin_name: str, *, env_var: str | None = None) -> AvailabilityStatus:
    """Locate bin_name, trying an explicit override before falling back to
    the usual OS lookup and then known install locations."""
    if env_var:
        override = os.environ.get(env_var)
        if override and Path(override).is_file():
            return AvailabilityStatus(True, Path(override), "env")

    which_result = shutil.which(bin_name)
    if which_result:
        return AvailabilityStatus(True, Path(which_result), "path")

    for candidate in KNOWN_INSTALL_PATHS.get(bin_name, ()):
        if candidate.is_file():
            return AvailabilityStatus(True, candidate, "known-location")

    return AvailabilityStatus(False, None, "not-found")
