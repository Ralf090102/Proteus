"""Converter contract every backend implements.

A Converter wraps exactly one (from_ext, to_ext) conversion pair behind a
typed interface, regardless of how the conversion is actually performed —
today's plan has concrete converters (Phase 3+) shell out to
LibreOffice/Pandoc as subprocesses or use an in-process library (pdf2docx,
PyMuPDF), but the contract itself doesn't assume that.

Extensions are bare, lowercase, no leading dot ("docx", not ".docx" or
"DOCX") — normalized once at the CLI/registry boundary so every converter
and registry entry can compare them directly.
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, NamedTuple

from pydantic import BaseModel, ConfigDict

from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConversionFailedError, ProteusError


class ConversionOptions(BaseModel):
    """Base class for per-conversion options.

    Empty for now — no converter needs a knob yet. extra="forbid" so a
    typo'd option fails loudly at construction rather than being silently
    ignored, matching lyra-mcp's StageConfig convention.
    """

    model_config = ConfigDict(extra="forbid")


class ConversionResult(BaseModel):
    """What a successful Converter.convert() call returns."""

    model_config = ConfigDict(extra="forbid")

    output_path: Path


def ensure_output_created(output_path: Path, backend_name: str) -> None:
    """Raise ConversionFailedError if output_path wasn't actually created.

    Shared final step for every converter's convert() — a backend
    reporting success (subprocess exit 0, a library call returning
    normally) doesn't guarantee it actually wrote the file.
    """
    if not output_path.exists():
        raise ConversionFailedError(
            f"{backend_name} reported success but {output_path} wasn't created"
        )
    if output_path.stat().st_size == 0:
        raise ConversionFailedError(
            f"{backend_name} reported success but {output_path} is empty"
        )


def atomic_write(
    output_path: Path, backend_name: str, write_fn: Callable[[Path], None]
) -> ConversionResult:
    """Shared write-to-temp/verify/replace-in mechanics for every
    Converter/Merger that writes its own output file directly (as opposed
    to LibreOfficeConverter, which stages output in a temp *directory*
    because soffice — not Proteus — picks the output filename, and
    finishes with shutil.move for cross-drive safety; that's a genuinely
    different problem and deliberately doesn't use this helper).

    write_fn(tmp_path) must produce the real output at tmp_path and raise
    ConversionFailedError itself on failure, with its own converter-
    specific verb/subject wording (e.g. "Pillow failed to convert
    {input_path}: {e}") — this function does NOT generically wrap
    write_fn's exceptions into a one-size-fits-all message, since the
    right wording (what verb, input_path vs. output_path as the subject)
    genuinely varies per caller and a shared template can't reproduce
    that without turning this into a multi-parameter, shallower interface.
    The bare `except Exception` below is a last-resort safety net only —
    for a write_fn that has a bug and forgets to wrap — not the primary
    error path; every Converter/Merger docstring in this codebase treats
    "never raise a bare Exception" as a hard invariant, worth defending
    even against a future write_fn's own mistake.

    Writes to a temp file in output_path's own directory (same drive, so
    os.replace() below is atomic) rather than letting write_fn target
    output_path directly — a mid-write failure must not destroy whatever
    was already at output_path (the exact data-loss bug independently
    found and fixed in converters/image.py and converters/pandoc.py
    before this helper existed to prevent it happening a third time).
    """
    tmp_output = output_path.with_name(f".proteus-tmp-{uuid.uuid4().hex}{output_path.suffix}")
    try:
        try:
            write_fn(tmp_output)
        except ProteusError:
            # Any typed Proteus error write_fn already raised on purpose
            # (ConversionFailedError with its own wording, or e.g.
            # ConverterUnavailableError from a subprocess helper like
            # pandoc.py's run_subprocess()) — propagate as-is, don't
            # reclassify it as the generic safety-net message below.
            raise
        except Exception as e:
            raise ConversionFailedError(
                f"{backend_name}: unexpected failure writing to {output_path}: {e}"
            ) from e

        ensure_output_created(tmp_output, backend_name)

        try:
            os.replace(tmp_output, output_path)
        except OSError as e:
            raise ConversionFailedError(
                f"{backend_name} produced {tmp_output} but couldn't move it to "
                f"{output_path} (destination may be open elsewhere): {e}"
            ) from e
    except Exception:
        tmp_output.unlink(missing_ok=True)
        raise

    return ConversionResult(output_path=output_path)


class ToolCheck(NamedTuple):
    """One external tool a converter depends on, paired with its resolved
    find_tool() status — e.g. ("soffice", AvailabilityStatus(...)).

    kind distinguishes an external binary ("tool", the default — resolved
    via find_tool(), fixed via an INSTALL_LINKS download page or
    `proteus install-deps`) from an optional Python package extra
    ("extra" — e.g. Pillow, resolved via a plain `import`, fixed via
    `uv tool install .[images]`, never a winget/download-link candidate).
    doctor()/install_deps() in cli.py branch on this to avoid printing a
    "not found" + broken download link for something that was never an
    external tool to begin with.
    """

    bin_name: str
    status: AvailabilityStatus
    kind: str = "tool"  # "tool" | "extra"


class Converter(ABC):
    """Base contract for a single (from_ext, to_ext) conversion pair."""

    from_ext: ClassVar[str]
    to_ext: ClassVar[str]

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this converter's required external tool is present on
        this machine (e.g. `soffice`/`pandoc` on PATH). `proteus doctor`
        and callers checking before a real conversion use this — see
        ConverterUnavailableError in core/errors.py."""
        raise NotImplementedError

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        """External tool(s) this converter depends on, each already
        resolved via find_tool(). Empty for a converter with no external
        dependency (e.g. one wrapping a hard Python library that's always
        available) — the default here, so no existing converter is forced
        to override it. `proteus doctor` uses this to explain *why* an
        unavailable converter is unavailable (and how to fix it) without
        needing to know anything converter-specific itself."""
        return ()

    @abstractmethod
    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        """Convert input_path to output_path.

        Implementations must raise a ProteusError subclass (see
        src/proteus/core/errors.py) on any failure, never a bare
        Exception, so callers can handle conversion failures uniformly
        regardless of backend.
        """
        raise NotImplementedError
