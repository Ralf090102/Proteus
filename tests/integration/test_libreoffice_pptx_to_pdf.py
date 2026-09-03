"""Opt-in integration test against a real LibreOffice install.

Run with `pytest -m integration` — needs `soffice` on PATH. Legacy .ppt
has no equivalent test here — see the comment in core/registry.py for why
(fixture-size cost vs. redundant proof, given PptToPdfConverter is the
same LibreOfficeConverter.convert() logic already exercised here).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.libreoffice import PptxToPdfConverter
from proteus.core.converter import ConversionOptions

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.pptx"


@pytest.mark.integration
def test_real_libreoffice_converts_sample_pptx_to_pdf(tmp_path):
    converter = PptxToPdfConverter()
    assert converter.is_available(), "soffice not found on PATH — install LibreOffice first"

    output_path = tmp_path / "sample.pdf"
    result = converter.convert(FIXTURE, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes()[:5] == b"%PDF-"


@pytest.mark.integration
def test_real_libreoffice_converts_a_unicode_and_space_named_pptx_file(tmp_path):
    # Same regression as the docx integration test: glob-based output
    # discovery must hold for pptx sources too, not just docx.
    converter = PptxToPdfConverter()
    assert converter.is_available(), "soffice not found on PATH — install LibreOffice first"

    input_path = tmp_path / "café résumé — v2.pptx"
    input_path.write_bytes(FIXTURE.read_bytes())
    output_path = tmp_path / "output.pdf"

    result = converter.convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes()[:5] == b"%PDF-"
