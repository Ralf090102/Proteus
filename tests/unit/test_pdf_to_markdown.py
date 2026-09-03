"""Unit tests for PdfToMarkdownConverter's availability/missing-pymupdf4llm
handling — simulates pymupdf4llm being absent via sys.modules, so no real
install is needed and these always run regardless of whether the optional
`markdown` extra is installed in this environment. Real-conversion tests
(which do need pymupdf4llm) live in test_pdf_to_markdown_real.py, a
separate module so pytest.importorskip there can skip that whole file
cleanly without affecting these."""

from __future__ import annotations

import sys

import pytest

from proteus.converters.pdf_extract import PdfToMarkdownConverter
from proteus.core.converter import ConversionOptions, ToolCheck
from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConverterUnavailableError


def test_is_available_false_when_pymupdf4llm_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)
    assert PdfToMarkdownConverter().is_available() is False


def test_convert_raises_converter_unavailable_when_pymupdf4llm_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)

    with pytest.raises(ConverterUnavailableError, match=r"uv tool install \.\[markdown\]"):
        PdfToMarkdownConverter().convert(
            tmp_path / "in.pdf", tmp_path / "out.md", ConversionOptions()
        )


def test_tool_checks_reports_extra_kind_when_pymupdf4llm_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)

    checks = PdfToMarkdownConverter().tool_checks()

    assert checks == (
        ToolCheck("pymupdf4llm", AvailabilityStatus(False, None, "not-found"), "extra"),
    )
