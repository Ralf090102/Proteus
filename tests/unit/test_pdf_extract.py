"""Unit tests for the PDF-source converters — pdf2docx/PyMuPDF are hard
dependencies (no external tool to mock), so these run real conversions
against the committed sample.pdf fixture."""

from __future__ import annotations

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
