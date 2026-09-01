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
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


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
