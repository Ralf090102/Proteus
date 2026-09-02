"""Pandoc-backed converters: docx <-> md.

One class per (from_ext, to_ext) pair, same pattern LibreOfficeConverter
established — CONVERTER_REGISTRY maps a pair to a type[Converter]
constructed with no args (core/registry.py), so a single class can't carry
two different from_ext/to_ext class vars. _PandocConverterBase holds the
shared subprocess-invocation logic; the two public classes just set which
pair and which Pandoc format names they are.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ToolCheck,
    ensure_output_created,
)
from proteus.core.dependencies import find_tool
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError
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

        # Write to a temp file in output_path's own directory (same drive,
        # so os.replace() below is atomic), not directly to output_path
        # via pandoc's own -o: if pandoc fails partway through writing
        # (crashed, disk full), a pre-existing file at output_path must
        # not be destroyed/truncated before the failure is even known —
        # same reasoning as converters/image.py's identical fix, applied
        # here since pandoc's -o has the same direct-to-destination
        # pattern LibreOffice deliberately avoids via its isolated outdir.
        tmp_output = output_path.with_name(
            f".proteus-tmp-{uuid.uuid4().hex}{output_path.suffix}"
        )
        try:
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

            ensure_output_created(tmp_output, "pandoc")

            try:
                os.replace(tmp_output, output_path)
            except OSError as e:
                raise ConversionFailedError(
                    f"pandoc produced {tmp_output} but couldn't move it to "
                    f"{output_path} (destination may be open elsewhere): {e}"
                ) from e
        except Exception:
            tmp_output.unlink(missing_ok=True)
            raise

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
