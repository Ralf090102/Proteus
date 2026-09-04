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

# Windowed-subsystem twin of the regular `proteus` console CLI (see
# [project.gui-scripts] in pyproject.toml) — every context-menu verb and
# Send To shortcut's Command points here instead of `proteus` itself, so a
# right-click/Send-To-launched conversion doesn't flash a console window.
PROTEUS_GUI_BIN = "proteus-gui"
PROTEUS_GUI_ENV_VAR = "PROTEUS_GUI_EXE_PATH"


@dataclass(frozen=True)
class AvailabilityStatus:
    available: bool
    path: Path | None
    source: str  # "env" | "path" | "known-location" | "package" | "not-found"


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
    # `uv tool install .`'s own default shim location for the windowed
    # `proteus-gui` exe (see [project.gui-scripts] in pyproject.toml) — the
    # context menu needs this same fallback (not just a bare shutil.which())
    # for the same reason LibreOffice/Pandoc do.
    "proteus-gui": (Path.home() / ".local" / "bin" / "proteus-gui.exe",),
}

# Hand-maintained alongside KNOWN_INSTALL_PATHS, for the same reason — used
# by `proteus doctor` (via Converter.tool_checks(), see core/converter.py)
# to point at where to get a missing tool instead of just saying "no."
INSTALL_LINKS: dict[str, str] = {
    "soffice": "https://www.libreoffice.org/download/download-libreoffice/",
    "pandoc": "https://pandoc.org/installing.html",
}

# winget package IDs for the tools above that have one — used by
# `proteus install-deps` to automate what INSTALL_LINKS otherwise just
# points the user at manually. Not every entry in INSTALL_LINKS needs a
# match here (a tool with no winget package would only ever show up in
# INSTALL_LINKS, install-deps falls back to listing it as manual-only).
WINGET_PACKAGE_IDS: dict[str, str] = {
    "soffice": "TheDocumentFoundation.LibreOffice",
    "pandoc": "JohnMacFarlane.Pandoc",
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


def resolve_proteus_gui_exe_path() -> Path:
    """Resolve the installed `proteus-gui` exe's own absolute path — the
    windowed twin of the regular `proteus` console CLI that every
    context-menu verb (windows/context_menu.py) and Send To shortcut
    (windows/sendto.py) actually invokes.

    Both callers launch this with no working directory or project-venv
    context of their own, so this needs a stable, global path — exactly
    what `uv tool install .` provides. Goes through find_tool() (env
    override -> PATH -> known `uv tool install` location) rather than a
    bare shutil.which(), for the same PATH-unreliability reason
    LibreOffice/Pandoc do.
    """
    status = find_tool(PROTEUS_GUI_BIN, env_var=PROTEUS_GUI_ENV_VAR)
    if not status.available:
        raise RuntimeError(
            "proteus-gui isn't on PATH. Run `uv tool install .` first so the shortcut "
            "has a stable exe path to point at."
        )
    return status.path.resolve()
