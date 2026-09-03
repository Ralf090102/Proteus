"""Unit tests for the PDF-source converters — pdf2docx/PyMuPDF are hard
dependencies (no external tool to mock), so these run real conversions
against the committed sample.pdf fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from docx import Document

from proteus.converters.pdf_extract import Pdf2DocxConverter, PyMuPdfTextExtractConverter
from proteus.core.converter import ConversionOptions
from proteus.core.errors import ConversionFailedError

SAMPLE_PDF = Path(__file__).parent.parent / "fixtures" / "sample.pdf"


def test_pdf2docx_is_available_always_true():
    assert Pdf2DocxConverter().is_available() is True


def test_pymupdf_is_available_always_true():
    assert PyMuPdfTextExtractConverter().is_available() is True


def test_pdf2docx_converts_sample_pdf_to_docx(tmp_path):
    output_path = tmp_path / "sample.docx"
    result = Pdf2DocxConverter().convert(SAMPLE_PDF, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()

    doc = Document(str(output_path))
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Proteus Sample Document" in all_text


def test_pymupdf_extracts_sample_pdf_text(tmp_path):
    output_path = tmp_path / "sample.txt"
    result = PyMuPdfTextExtractConverter().convert(SAMPLE_PDF, output_path, ConversionOptions())

    assert result.output_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "Proteus Sample Document" in text
    assert "First item" in text


def test_pdf2docx_raises_conversion_failed_for_invalid_pdf(tmp_path):
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    with pytest.raises(ConversionFailedError):
        Pdf2DocxConverter().convert(bad_pdf, tmp_path / "out.docx", ConversionOptions())


def test_pymupdf_raises_conversion_failed_for_invalid_pdf(tmp_path):
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    with pytest.raises(ConversionFailedError):
        PyMuPdfTextExtractConverter().convert(bad_pdf, tmp_path / "out.txt", ConversionOptions())


def test_pymupdf_convert_does_not_destroy_pre_existing_output_on_failure(tmp_path):
    # Regression: this converter used to write straight to output_path
    # (output_path.write_text(...)), which would destroy a pre-existing
    # file on a mid-extraction failure — the same data-loss class fixed
    # elsewhere (converters/pandoc.py, converters/image.py,
    # PdfToMarkdownConverter). Now uses the same atomic temp-file +
    # os.replace() pattern.
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    output_path = tmp_path / "out.txt"
    output_path.write_text("important pre-existing content")

    with pytest.raises(ConversionFailedError):
        PyMuPdfTextExtractConverter().convert(bad_pdf, output_path, ConversionOptions())

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_pdf2docx_import_failure_surfaces_as_conversion_failed(monkeypatch, tmp_path):
    # Regression: the lazy `from pdf2docx import Converter` sat outside
    # convert()'s try/except — a broken/partial pdf2docx install would
    # crash with a raw ImportError instead of ConversionFailedError.
    # `None` in sys.modules is the standard way to force `import x` to
    # raise ImportError without needing pdf2docx to actually be missing.
    monkeypatch.setitem(sys.modules, "pdf2docx", None)

    with pytest.raises(ConversionFailedError):
        Pdf2DocxConverter().convert(SAMPLE_PDF, tmp_path / "out.docx", ConversionOptions())


def test_pymupdf_import_failure_surfaces_as_conversion_failed(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pymupdf", None)

    with pytest.raises(ConversionFailedError):
        PyMuPdfTextExtractConverter().convert(
            SAMPLE_PDF, tmp_path / "out.txt", ConversionOptions()
        )
