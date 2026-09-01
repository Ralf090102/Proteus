"""In-process PDF-source converters: pdf -> docx (pdf2docx), pdf -> txt
(PyMuPDF).

Unlike LibreOffice/Pandoc, these wrap Python libraries directly — no
external binary, no subprocess boundary. Both libraries are hard
dependencies (see pyproject.toml), not optional installs, so
is_available() is simply True.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from pdf2docx import Converter as Pdf2DocxLibConverter

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ensure_output_created,
)
from proteus.core.errors import ConversionFailedError


class Pdf2DocxConverter(Converter):
    from_ext = "pdf"
    to_ext = "docx"

    def is_available(self) -> bool:
        return True

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        cv = None
        try:
            cv = Pdf2DocxLibConverter(str(input_path))
            cv.convert(str(output_path))
        except Exception as e:
            # pdf2docx has no stable typed-exception contract to catch
            # narrowly — any failure here must still surface as a
            # ProteusError, never a bare exception.
            raise ConversionFailedError(f"pdf2docx failed to convert {input_path}: {e}") from e
        finally:
            if cv is not None:
                try:
                    cv.close()
                except Exception:
                    # A close()-time failure shouldn't mask the real
                    # convert() outcome above (or override a genuine
                    # success) — cleanup is best-effort here.
                    pass

        ensure_output_created(output_path, "pdf2docx")
        return ConversionResult(output_path=output_path)


class PyMuPdfTextExtractConverter(Converter):
    from_ext = "pdf"
    to_ext = "txt"

    def is_available(self) -> bool:
        return True

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        """Extract text via PyMuPDF (imported as `pymupdf` — the `fitz`
        alias is deprecated as of the pinned version)."""
        try:
            with pymupdf.open(str(input_path)) as doc:
                text = "\n".join(page.get_text() for page in doc)
            output_path.write_text(text, encoding="utf-8")
        except Exception as e:
            raise ConversionFailedError(
                f"PyMuPDF failed to extract text from {input_path}: {e}"
            ) from e

        return ConversionResult(output_path=output_path)
