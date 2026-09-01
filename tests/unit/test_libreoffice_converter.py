"""Unit tests for LibreOfficeConverter — find_tool and run_subprocess are
mocked, so no real LibreOffice install is needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters import libreoffice as libreoffice_module
from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.core.converter import ConversionOptions
from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError

_SOFFICE_PATH = Path("/usr/bin/soffice")


def _available(path: Path = _SOFFICE_PATH) -> AvailabilityStatus:
    return AvailabilityStatus(True, path, "path")


def _unavailable() -> AvailabilityStatus:
    return AvailabilityStatus(False, None, "not-found")


def test_is_available_reflects_find_tool(monkeypatch):
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())
    assert LibreOfficeConverter().is_available() is True

    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _unavailable())
    assert LibreOfficeConverter().is_available() is False


def test_convert_raises_converter_unavailable_when_soffice_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _unavailable())
    converter = LibreOfficeConverter()
    with pytest.raises(ConverterUnavailableError):
        converter.convert(tmp_path / "in.docx", tmp_path / "out.pdf", ConversionOptions())


def test_convert_invokes_resolved_soffice_path_and_renames_output(monkeypatch, tmp_path):
    resolved_path = tmp_path / "known-location" / "soffice.exe"
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available(resolved_path))

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "renamed.pdf"

    captured_cmd = {}

    def fake_run_subprocess(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        # Simulate LibreOffice writing <stem>.pdf into --outdir.
        (tmp_path / "in.pdf").write_bytes(b"%PDF-fake")

    monkeypatch.setattr(libreoffice_module, "run_subprocess", fake_run_subprocess)

    converter = LibreOfficeConverter()
    result = converter.convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    assert not (tmp_path / "in.pdf").exists()
    # Regression: the resolved path from find_tool() is what gets
    # invoked, not the bare "soffice" name — matters when the tool was
    # only found via env override or a known install location, not PATH.
    assert captured_cmd["cmd"][0] == str(resolved_path)


def test_convert_raises_conversion_failed_if_expected_output_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())
    monkeypatch.setattr(libreoffice_module, "run_subprocess", lambda cmd, **kwargs: None)

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "out.pdf"

    converter = LibreOfficeConverter()
    with pytest.raises(ConversionFailedError):
        converter.convert(input_path, output_path, ConversionOptions())


def test_convert_raises_conversion_failed_if_missing_output_with_matching_name(
    monkeypatch, tmp_path
):
    # Regression: when output_path already matches <input-stem>.pdf (the
    # default, no -o, invocation), the "did LibreOffice actually produce
    # this?" check must still run — soffice can exit 0 without writing
    # anything under profile-lock contention.
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())
    monkeypatch.setattr(libreoffice_module, "run_subprocess", lambda cmd, **kwargs: None)

    input_path = tmp_path / "doc.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "doc.pdf"  # same stem as input -> produced == output_path

    converter = LibreOfficeConverter()
    with pytest.raises(ConversionFailedError):
        converter.convert(input_path, output_path, ConversionOptions())


def test_convert_raises_conversion_failed_when_rename_fails(monkeypatch, tmp_path):
    # Regression: a locked destination (e.g. open in a PDF viewer) must
    # surface as a ProteusError, not a bare PermissionError.
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "renamed.pdf"

    def fake_run_subprocess(cmd, **kwargs):
        (tmp_path / "in.pdf").write_bytes(b"%PDF-fake")

    monkeypatch.setattr(libreoffice_module, "run_subprocess", fake_run_subprocess)

    def raise_permission_error(self, target):
        raise PermissionError("destination is open elsewhere")

    monkeypatch.setattr(libreoffice_module.Path, "replace", raise_permission_error)

    converter = LibreOfficeConverter()
    with pytest.raises(ConversionFailedError):
        converter.convert(input_path, output_path, ConversionOptions())
