"""Pandoc-backed converters: docx <-> md.

One class per (from_ext, to_ext) pair, same pattern LibreOfficeConverter
established — CONVERTER_REGISTRY maps a pair to a type[Converter]
constructed with no args (core/registry.py), so a single class can't carry
two different from_ext/to_ext class vars. _PandocConverterBase holds the
shared subprocess-invocation logic; the two public classes just set which
pair and which Pandoc format names they are.
"""

from __future__ import annotations

from pathlib import Path

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ToolCheck,
    atomic_write,
)
from proteus.core.dependencies import find_tool
from proteus.core.errors import ConverterUnavailableError
from proteus.core.subprocess_utils import run_subprocess

PANDOC_BIN = "pandoc"
PANDOC_ENV_VAR = "PROTEUS_PANDOC_PATH"


class _PandocConverterBase(Converter):
    """Shared Pandoc invocation. Subclasses set from_ext/to_ext (Proteus's
    own extension vocabulary) plus pandoc_from_format/pandoc_to_format
    (Pandoc's own -f/-t format names, not always the same string)."""

    pandoc_from_format: str
    pandoc_to_format: str

    def is_available(self) -> bool:
        return find_tool(PANDOC_BIN, env_var=PANDOC_ENV_VAR).available

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        return (ToolCheck(PANDOC_BIN, find_tool(PANDOC_BIN, env_var=PANDOC_ENV_VAR)),)

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        status = find_tool(PANDOC_BIN, env_var=PANDOC_ENV_VAR)
        if not status.available:
            raise ConverterUnavailableError(
                f"Pandoc ({PANDOC_BIN}) not found. Install it to convert "
                f"{self.from_ext}->{self.to_ext}."
            )

        def write(tmp_output: Path) -> None:
            # -o writes directly to whatever path it's given, not
            # atomically — atomic_write() (core/converter.py) is what
            # keeps a mid-write pandoc failure (crashed, disk full) from
            # destroying a pre-existing file at output_path; this only
            # needs to target tmp_output. run_subprocess() already raises
            # ConversionFailedError/ConverterUnavailableError itself on
            # failure, so no extra wrapping is needed here.
            run_subprocess(
                [
                    str(status.path),
                    "-f",
                    self.pandoc_from_format,
                    "-t",
                    self.pandoc_to_format,
                    "-o",
                    str(tmp_output),
                    str(input_path),
                ]
            )

        return atomic_write(output_path, "pandoc", write)


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
