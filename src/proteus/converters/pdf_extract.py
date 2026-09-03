"""In-process PDF-source converters: pdf -> docx (pdf2docx), pdf -> txt
(PyMuPDF), pdf -> md (pymupdf4llm).

Unlike LibreOffice/Pandoc, these wrap Python libraries directly — no
external binary, no subprocess boundary. pdf2docx/pymupdf are hard
dependencies (see pyproject.toml), not optional installs, so
is_available() is simply True for those two. pymupdf4llm is different —
see PdfToMarkdownConverter below.

pdf2docx/pymupdf are imported lazily, inside convert() rather than at
module level: pdf2docx's own top-level `import fitz` prints a
user-visible deprecation warning ("`fitz` API is deprecated ... use
`import pymupdf` instead") at import time, and core/registry.py imports
every converter module eagerly regardless of which pair is actually being
run. A module-level import here meant that warning showed up on *every*
Proteus invocation, including plain docx->pdf runs that never touch these
libraries at all — confusing enough that it looked like docx->pdf itself
was broken. Deferring the import means it only appears for pdf->docx /
pdf->txt, the two pairs that actually need it.
"""

from __future__ import annotations

import io
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
from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError

PYMUPDF4LLM_EXTRA_NAME = "pymupdf4llm"
PYMUPDF4LLM_INSTALL_HINT = "uv tool install .[markdown]"


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
            from pdf2docx import Converter as Pdf2DocxLibConverter

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
            import pymupdf

            with pymupdf.open(str(input_path)) as doc:
                text = "\n".join(page.get_text() for page in doc)
            output_path.write_text(text, encoding="utf-8")
        except Exception as e:
            raise ConversionFailedError(
                f"PyMuPDF failed to extract text from {input_path}: {e}"
            ) from e

        return ConversionResult(output_path=output_path)


class PdfToMarkdownConverter(Converter):
    """Markdown-preserving PDF extraction via pymupdf4llm (headings,
    lists, tables — not just flat text like PyMuPdfTextExtractConverter
    above).

    Unlike pdf2docx/pymupdf, pymupdf4llm is a genuinely optional install
    (the `markdown` extra in pyproject.toml, not a base dependency) —
    same reasoning as converters/image.py's Pillow extra: it pulls in a
    much heavier transitive footprint (an ONNX layout model, onnxruntime,
    networkx) than this single feature's value justifies as a hard
    dependency. is_available() actually probes for it rather than always
    returning True.
    """

    from_ext = "pdf"
    to_ext = "md"

    def is_available(self) -> bool:
        try:
            import pymupdf4llm  # noqa: F401
        except ImportError:
            return False
        return True

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        try:
            import pymupdf4llm

            status = AvailabilityStatus(True, Path(pymupdf4llm.__file__).parent, "package")
        except ImportError:
            status = AvailabilityStatus(False, None, "not-found")
        return (ToolCheck(PYMUPDF4LLM_EXTRA_NAME, status, kind="extra"),)

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        try:
            import pymupdf4llm
        except ImportError as e:
            raise ConverterUnavailableError(
                f"pymupdf4llm is not installed. Install the optional markdown-conversion "
                f"extra: {PYMUPDF4LLM_INSTALL_HINT}"
            ) from e

        # Same atomic-write pattern as converters/image.py: write to a temp
        # file in output_path's own directory, then os.replace() it in —
        # writing straight to output_path would destroy a pre-existing file
        # on a mid-conversion failure (the same data-loss class fixed
        # 2026-09-02 in converters/pandoc.py and converters/image.py).
        tmp_output = output_path.with_name(f".proteus-tmp-{uuid.uuid4().hex}{output_path.suffix}")
        try:
            try:
                # pymupdf4llm prints diagnostic banners ("Document parser
                # messages", OCR-engine notices) whenever layout/OCR
                # processing has anything to report — not just at import
                # time, so the lazy-import trick above doesn't cover it.
                # It goes through pymupdf's own message sink
                # (pymupdf.message(), written directly to the stream
                # pymupdf.set_messages() points at — a plain
                # contextlib.redirect_stdout on Python's sys.stdout does
                # NOT catch this, confirmed empirically: pymupdf's sink is
                # independent of sys.stdout). Under proteus-gui.exe (the
                # windowed context-menu entry point, no console attached)
                # letting this reach the real stream risks a crash if
                # pymupdf's default sink resolves to a None stdout;
                # redirect it to a throwaway buffer for the duration of
                # this call and restore the original sink afterward so
                # other pymupdf usage in this process (Pdf2DocxConverter,
                # PyMuPdfTextExtractConverter) isn't affected.
                import pymupdf

                original_message_stream = pymupdf._g_out_message
                pymupdf.set_messages(stream=io.StringIO())
                try:
                    md_text = pymupdf4llm.to_markdown(str(input_path))
                finally:
                    pymupdf.set_messages(stream=original_message_stream)
                tmp_output.write_text(md_text, encoding="utf-8")
            except Exception as e:
                raise ConversionFailedError(
                    f"pymupdf4llm failed to convert {input_path}: {e}"
                ) from e

            ensure_output_created(tmp_output, "pymupdf4llm")

            try:
                os.replace(tmp_output, output_path)
            except OSError as e:
                raise ConversionFailedError(
                    f"pymupdf4llm produced {tmp_output} but couldn't move it to "
                    f"{output_path} (destination may be open elsewhere): {e}"
                ) from e
        except Exception:
            tmp_output.unlink(missing_ok=True)
            raise

        return ConversionResult(output_path=output_path)
