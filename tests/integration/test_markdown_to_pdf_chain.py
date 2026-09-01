"""Opt-in integration test against real Pandoc + LibreOffice.

Run with `pytest -m integration` — needs both `pandoc` and `soffice` on PATH.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.chains import MarkdownToPdfChainConverter
from proteus.core.converter import ConversionOptions

SAMPLE_MD = Path(__file__).parent.parent / "fixtures" / "sample.md"


@pytest.mark.integration
def test_real_chain_converts_markdown_to_pdf(tmp_path):
    converter = MarkdownToPdfChainConverter()
    assert converter.is_available(), "pandoc and/or soffice not found on PATH"

    output_path = tmp_path / "sample.pdf"
    result = converter.convert(SAMPLE_MD, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes()[:5] == b"%PDF-"
