"""Opt-in integration test against a real LibreOffice install.

Run with `pytest -m integration` — needs `soffice` on PATH.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.core.converter import ConversionOptions

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.docx"


@pytest.mark.integration
def test_real_libreoffice_converts_sample_docx_to_pdf(tmp_path):
    converter = LibreOfficeConverter()
    assert converter.is_available(), "soffice not found on PATH — install LibreOffice first"

    output_path = tmp_path / "sample.pdf"
    result = converter.convert(FIXTURE, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes()[:5] == b"%PDF-"


@pytest.mark.integration
def test_real_libreoffice_converts_a_unicode_and_space_named_file(tmp_path):
    # Confirms the glob-based output-discovery fix actually holds against
    # the real tool, not just a mock: copy the fixture to a temp file
    # whose name has unicode + space content (not a committed fixture, to
    # avoid git/encoding portability concerns) and convert it for real.
    converter = LibreOfficeConverter()
    assert converter.is_available(), "soffice not found on PATH — install LibreOffice first"

    input_path = tmp_path / "café résumé — v2.docx"
    input_path.write_bytes(FIXTURE.read_bytes())
    output_path = tmp_path / "output.pdf"

    result = converter.convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes()[:5] == b"%PDF-"
