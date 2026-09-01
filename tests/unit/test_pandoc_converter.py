"""Unit tests for the Pandoc-backed converters — find_tool and
run_subprocess are mocked, so no real Pandoc install is needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters import pandoc as pandoc_module
from proteus.converters.pandoc import PANDOC_BIN, DocxToMarkdownConverter, MarkdownToDocxConverter
from proteus.core.converter import ConversionOptions, ToolCheck
from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError

_PANDOC_PATH = Path("/usr/bin/pandoc")


def _available(path: Path = _PANDOC_PATH) -> AvailabilityStatus:
    return AvailabilityStatus(True, path, "path")


def _unavailable() -> AvailabilityStatus:
    return AvailabilityStatus(False, None, "not-found")


def test_is_available_reflects_find_tool(monkeypatch):
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: _available())
    assert DocxToMarkdownConverter().is_available() is True

    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: _unavailable())
    assert DocxToMarkdownConverter().is_available() is False


def test_tool_checks_reflects_find_tool(monkeypatch):
    status = _available(Path("/opt/known-location/pandoc"))
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: status)
    assert DocxToMarkdownConverter().tool_checks() == (ToolCheck(PANDOC_BIN, status),)


def test_convert_raises_converter_unavailable_when_pandoc_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: _unavailable())
    converter = DocxToMarkdownConverter()
    with pytest.raises(ConverterUnavailableError):
        converter.convert(tmp_path / "in.docx", tmp_path / "out.md", ConversionOptions())


def test_docx_to_markdown_invokes_resolved_pandoc_path_with_correct_formats(monkeypatch, tmp_path):
    resolved_path = tmp_path / "known-location" / "pandoc.exe"
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: _available(resolved_path))

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "out.md"

    captured_cmd = {}

    def fake_run_subprocess(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        output_path.write_text("# converted")

    monkeypatch.setattr(pandoc_module, "run_subprocess", fake_run_subprocess)

    result = DocxToMarkdownConverter().convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    cmd = captured_cmd["cmd"]
    # Regression: the resolved path from find_tool() is what gets
    # invoked, not the bare "pandoc" name.
    assert cmd[0] == str(resolved_path)
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "docx"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "gfm"
    assert str(output_path) in cmd
    assert str(input_path) in cmd


def test_markdown_to_docx_invokes_pandoc_with_correct_formats(monkeypatch, tmp_path):
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: _available())

    input_path = tmp_path / "in.md"
    input_path.write_text("# placeholder")
    output_path = tmp_path / "out.docx"

    captured_cmd = {}

    def fake_run_subprocess(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        output_path.write_bytes(b"placeholder-docx")

    monkeypatch.setattr(pandoc_module, "run_subprocess", fake_run_subprocess)

    result = MarkdownToDocxConverter().convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    cmd = captured_cmd["cmd"]
    assert cmd[cmd.index("-f") + 1] == "gfm"
    assert cmd[cmd.index("-t") + 1] == "docx"


def test_convert_raises_conversion_failed_if_output_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: _available())
    monkeypatch.setattr(pandoc_module, "run_subprocess", lambda cmd, **kwargs: None)

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "out.md"  # never created by the fake run_subprocess

    converter = DocxToMarkdownConverter()
    with pytest.raises(ConversionFailedError):
        converter.convert(input_path, output_path, ConversionOptions())
