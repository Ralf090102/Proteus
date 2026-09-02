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

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, NamedTuple

from pydantic import BaseModel, ConfigDict

from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConversionFailedError


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
