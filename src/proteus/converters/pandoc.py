"""Pandoc-backed converters: docx <-> md.

One class per (from_ext, to_ext) pair, same pattern LibreOfficeConverter
established — CONVERTER_REGISTRY maps a pair to a type[Converter]
constructed with no args (core/registry.py), so a single class can't carry
two different from_ext/to_ext class vars. _PandocConverterBase holds the
shared subprocess-invocation logic; the two public classes just set which
pair and which Pandoc format names they are.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from proteus.core.converter import ConversionOptions, ConversionResult, Converter
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError
from proteus.core.subprocess_utils import run_subprocess

PANDOC_BIN = "pandoc"


class _PandocConverterBase(Converter):
    """Shared Pandoc invocation. Subclasses set from_ext/to_ext (Proteus's
    own extension vocabulary) plus pandoc_from_format/pandoc_to_format
    (Pandoc's own -f/-t format names, not always the same string)."""

    pandoc_from_format: str
    pandoc_to_format: str

    def is_available(self) -> bool:
        return shutil.which(PANDOC_BIN) is not None

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        if not self.is_available():
            raise ConverterUnavailableError(
                f"Pandoc ({PANDOC_BIN}) not found on PATH. Install it to convert "
                f"{self.from_ext}->{self.to_ext}."
            )

        run_subprocess(
            [
                PANDOC_BIN,
                "-f",
                self.pandoc_from_format,
                "-t",
                self.pandoc_to_format,
                "-o",
                str(output_path),
                str(input_path),
            ]
        )

        if not output_path.exists():
            raise ConversionFailedError(
                f"pandoc reported success but {output_path} wasn't created"
            )

        return ConversionResult(output_path=output_path)


class DocxToMarkdownConverter(_PandocConverterBase):
    from_ext = "docx"
    to_ext = "md"
    # GitHub-flavored markdown — better round-trip fidelity for lists,
    # tables, and code fences than Pandoc's default "markdown" dialect.
    pandoc_from_format = "docx"
    pandoc_to_format = "gfm"


class MarkdownToDocxConverter(_PandocConverterBase):
    from_ext = "md"
    to_ext = "docx"
    pandoc_from_format = "gfm"
    pandoc_to_format = "docx"
