"""Shared subprocess-boundary helper.

Backend-agnostic — knows nothing about LibreOffice or Pandoc specifically
(beyond the one LibreOffice-specific profile helper below, kept here since
it's the only external-tool quirk that needs subprocess-level plumbing).
Every converter that shells out to an external tool (LibreOffice now,
Pandoc in Phase 4) calls run_subprocess() so error handling and Windows
console-flash suppression live in exactly one place.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from proteus.core.errors import ConversionFailedError, ConverterUnavailableError

_WINDOWS_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run_subprocess(
    cmd: Sequence[str], *, timeout_s: float = 120.0, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run cmd, capturing stdout/stderr as text, with no console window
    flashing on Windows (relevant for a right-click-triggered conversion,
    which has no console attached at all).

    Raises ConverterUnavailableError if cmd[0] can't be launched (binary
    missing), ConversionFailedError on a non-zero exit or a timeout —
    callers don't need their own subprocess error handling.
    """
    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            cwd=cwd,
            creationflags=_WINDOWS_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as e:
        raise ConversionFailedError(f"{cmd[0]} timed out after {timeout_s}s") from e
    except OSError as e:
        raise ConverterUnavailableError(f"Could not launch {cmd[0]!r}: {e}") from e

    if result.returncode != 0:
        raise ConversionFailedError(
            f"{cmd[0]} exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


@contextmanager
def isolated_libreoffice_profile() -> Iterator[str]:
    """Yields a `-env:UserInstallation=file:///...` arg pointing at a fresh
    temp profile dir, deleted on exit.

    Each headless LibreOffice call needs its own profile dir — sharing the
    default one across repeated/back-to-back invocations (e.g. running the
    test suite, or two conversions in quick succession) causes lock
    contention that makes soffice silently fail to start.
    """
    with tempfile.TemporaryDirectory(prefix="proteus-soffice-") as tmp:
        profile_uri = Path(tmp).resolve().as_uri()
        yield f"-env:UserInstallation={profile_uri}"
