"""Real-conversion tests for PdfToMarkdownConverter.

pymupdf4llm is an optional install (the `markdown` extra), not a hard
dependency like pdf2docx/PyMuPDF — importorskip at module level means this
whole file skips cleanly in an environment where the extra isn't
installed, rather than assuming it's always present. Availability/
missing-pymupdf4llm tests (which must always run) live in the separate
test_pdf_to_markdown.py instead."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pymupdf4llm")

from proteus.converters.pdf_extract import PdfToMarkdownConverter  # noqa: E402
from proteus.core.converter import ConversionOptions  # noqa: E402
from proteus.core.errors import ConversionFailedError  # noqa: E402

SAMPLE_PDF = Path(__file__).parent.parent / "fixtures" / "sample.pdf"


def test_converts_sample_pdf_to_markdown_with_heading(tmp_path):
    output_path = tmp_path / "sample.md"
    result = PdfToMarkdownConverter().convert(SAMPLE_PDF, output_path, ConversionOptions())

    assert result.output_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "Proteus Sample Document" in text
    assert "First item" in text


def test_convert_raises_conversion_failed_for_invalid_pdf(tmp_path):
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    with pytest.raises(ConversionFailedError):
        PdfToMarkdownConverter().convert(bad_pdf, tmp_path / "out.md", ConversionOptions())


def test_convert_does_not_destroy_pre_existing_output_on_failure(tmp_path):
    # Regression: writing straight to output_path would destroy whatever
    # was already there on a mid-conversion failure — same data-loss class
    # fixed 2026-09-02 in converters/pandoc.py and converters/image.py.
    # The atomic temp-file + os.replace() pattern must hold here too.
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    output_path = tmp_path / "out.md"
    output_path.write_text("important pre-existing content")

    with pytest.raises(ConversionFailedError):
        PdfToMarkdownConverter().convert(bad_pdf, output_path, ConversionOptions())

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_tool_checks_reports_resolved_path_when_pymupdf4llm_available():
    checks = PdfToMarkdownConverter().tool_checks()
    assert len(checks) == 1
    bin_name, status, kind = checks[0]
    assert bin_name == "pymupdf4llm"
    assert kind == "extra"
    assert status.available is True
    assert status.path is not None


def test_convert_failure_surfaces_pymupdf_diagnostic_text(monkeypatch, tmp_path):
    # Regression: pymupdf4llm's diagnostic banners (routed through
    # pymupdf's own message sink, redirected to a throwaway buffer for
    # the duration of the call) used to be discarded unconditionally —
    # real debugging context (e.g. corrupt-xref recovery notices) that
    # would otherwise vanish on a genuine failure. Must now be folded
    # into the raised ConversionFailedError.
    import pymupdf
    import pymupdf4llm

    def fake_to_markdown(path):
        pymupdf.message("a diagnostic banner explaining the real problem")
        raise RuntimeError("boom")

    monkeypatch.setattr(pymupdf4llm, "to_markdown", fake_to_markdown)

    with pytest.raises(ConversionFailedError, match="a diagnostic banner explaining"):
        PdfToMarkdownConverter().convert(SAMPLE_PDF, tmp_path / "out.md", ConversionOptions())
