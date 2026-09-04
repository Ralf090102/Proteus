"""Unit tests for PdfMerger — pymupdf is a hard dependency (no external
tool to mock), so these run real merges against the committed sample.pdf/
sample2.pdf fixtures, same "no fake/double" convention as
test_pdf_extract.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from proteus.converters.merge import PdfMerger
from proteus.core.errors import ConversionFailedError

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_PDF = FIXTURES / "sample.pdf"
SAMPLE2_PDF = FIXTURES / "sample2.pdf"


def test_is_available_always_true():
    assert PdfMerger().is_available() is True


def test_merges_two_pdfs_into_one_with_combined_page_count(tmp_path):
    import pymupdf

    with pymupdf.open(SAMPLE_PDF) as d1, pymupdf.open(SAMPLE2_PDF) as d2:
        expected_pages = d1.page_count + d2.page_count

    output_path = tmp_path / "merged.pdf"
    result = PdfMerger().merge([SAMPLE_PDF, SAMPLE2_PDF], output_path)

    assert result.output_path == output_path
    with pymupdf.open(output_path) as merged:
        assert merged.page_count == expected_pages
        all_text = "\n".join(page.get_text() for page in merged)
    assert "Proteus Sample Document" in all_text
    assert "Second Sample PDF Fixture" in all_text


def test_merge_preserves_input_order(tmp_path):
    # The caller (cli.py's merge command) is responsible for sorting
    # input_paths before calling merge() — this just confirms merge()
    # itself doesn't reorder whatever list it's handed.
    import pymupdf

    output_path = tmp_path / "merged.pdf"
    PdfMerger().merge([SAMPLE2_PDF, SAMPLE_PDF], output_path)

    with pymupdf.open(output_path) as merged:
        assert "Second Sample PDF Fixture" in merged[0].get_text()


def test_merge_raises_conversion_failed_for_invalid_pdf(tmp_path):
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    with pytest.raises(ConversionFailedError):
        PdfMerger().merge([SAMPLE_PDF, bad_pdf], tmp_path / "out.pdf")


def test_merge_does_not_destroy_pre_existing_output_on_failure(tmp_path):
    bad_pdf = tmp_path / "not-a-real.pdf"
    bad_pdf.write_bytes(b"this is not a PDF")

    output_path = tmp_path / "out.pdf"
    output_path.write_text("important pre-existing content")

    with pytest.raises(ConversionFailedError):
        PdfMerger().merge([SAMPLE_PDF, bad_pdf], output_path)

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_import_failure_surfaces_as_conversion_failed(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pymupdf", None)

    with pytest.raises(ConversionFailedError):
        PdfMerger().merge([SAMPLE_PDF, SAMPLE2_PDF], tmp_path / "out.pdf")
