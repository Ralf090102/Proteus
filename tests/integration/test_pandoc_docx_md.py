"""Opt-in integration tests against a real Pandoc install.

Run with `pytest -m integration` — needs `pandoc` on PATH.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.pandoc import DocxToMarkdownConverter, MarkdownToDocxConverter
from proteus.core.converter import ConversionOptions

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_DOCX = FIXTURES / "sample.docx"
SAMPLE_MD = FIXTURES / "sample.md"


@pytest.mark.integration
def test_real_pandoc_converts_docx_to_markdown(tmp_path):
    converter = DocxToMarkdownConverter()
    assert converter.is_available(), "pandoc not found on PATH — install Pandoc first"

    output_path = tmp_path / "sample.md"
    result = converter.convert(SAMPLE_DOCX, output_path, ConversionOptions())

    assert result.output_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "Proteus Sample Document" in text
    assert "First item" in text


@pytest.mark.integration
def test_real_pandoc_converts_markdown_to_docx(tmp_path):
    converter = MarkdownToDocxConverter()
    assert converter.is_available(), "pandoc not found on PATH — install Pandoc first"

    output_path = tmp_path / "sample.docx"
    result = converter.convert(SAMPLE_MD, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
