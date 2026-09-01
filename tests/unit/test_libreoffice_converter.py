"""Unit tests for LibreOfficeConverter — find_tool and run_subprocess are
mocked, so no real LibreOffice install is needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters import libreoffice as libreoffice_module
from proteus.converters.libreoffice import SOFFICE_BIN, LibreOfficeConverter
from proteus.core.converter import ConversionOptions, ToolCheck
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


def test_tool_checks_reflects_find_tool(monkeypatch):
    status = _available(Path("/opt/known-location/soffice"))
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: status)
    assert LibreOfficeConverter().tool_checks() == (ToolCheck(SOFFICE_BIN, status),)


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
        # Simulate LibreOffice writing <stem>.pdf into whatever --outdir
        # the real code passed (an isolated temp dir, not output_path's
        # own directory — see the collision regression test below).
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "in.pdf").write_bytes(b"%PDF-fake")

    monkeypatch.setattr(libreoffice_module, "run_subprocess", fake_run_subprocess)

    converter = LibreOfficeConverter()
    result = converter.convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    # Regression: the resolved path from find_tool() is what gets
    # invoked, not the bare "soffice" name — matters when the tool was
    # only found via env override or a known install location, not PATH.
    assert captured_cmd["cmd"][0] == str(resolved_path)
    # --outdir must not be output_path's own directory — see the
    # collision regression test below for why.
    outdir_used = Path(captured_cmd["cmd"][captured_cmd["cmd"].index("--outdir") + 1])
    assert outdir_used != tmp_path


def test_convert_raises_conversion_failed_if_expected_output_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())
    monkeypatch.setattr(libreoffice_module, "run_subprocess", lambda cmd, **kwargs: None)

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "out.pdf"

    converter = LibreOfficeConverter()
    with pytest.raises(ConversionFailedError):
        converter.convert(input_path, output_path, ConversionOptions())


def test_convert_does_not_clobber_unrelated_same_stem_file_in_destination_dir(
    monkeypatch, tmp_path
):
    # Regression (real bug, hit for real this session): LibreOffice always
    # writes its raw output as <input-stem>.pdf directly into --outdir. If
    # that pointed at the real destination directory, a pre-existing
    # unrelated file sharing the input's stem would get silently
    # overwritten before our own rename step moved it away. --outdir must
    # be an isolated temp dir, never the real destination.
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())

    input_path = tmp_path / "doc.docx"
    input_path.write_text("placeholder")

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    unrelated_existing = dest_dir / "doc.pdf"  # same stem as input.docx
    unrelated_existing.write_bytes(b"pre-existing unrelated content")

    output_path = dest_dir / "renamed.pdf"

    def fake_run_subprocess(cmd, **kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        assert outdir != dest_dir, "must not write directly into the real destination dir"
        (outdir / "doc.pdf").write_bytes(b"%PDF-fake-real-output")

    monkeypatch.setattr(libreoffice_module, "run_subprocess", fake_run_subprocess)

    converter = LibreOfficeConverter()
    result = converter.convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.read_bytes() == b"%PDF-fake-real-output"
    # The unrelated pre-existing file must survive completely untouched.
    assert unrelated_existing.read_bytes() == b"pre-existing unrelated content"


def test_convert_moves_output_via_shutil_move_not_path_replace(monkeypatch, tmp_path):
    # Regression: Path.replace()/os.replace() cannot cross drive letters
    # on Windows (no MOVEFILE_COPY_ALLOWED fallback) — since the staging
    # dir is now a system temp dir (usually on C:) and the requested
    # output can be on any drive (this repo lives on D:), the move must
    # go through shutil.move(), which falls back to copy+delete when
    # os.rename() can't do it directly. A regression back to
    # Path.replace() would break every conversion whose output isn't on
    # the same drive as %TEMP%.
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "renamed.pdf"

    def fake_run_subprocess(cmd, **kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "in.pdf").write_bytes(b"%PDF-fake")

    monkeypatch.setattr(libreoffice_module, "run_subprocess", fake_run_subprocess)

    move_calls = []
    real_move = libreoffice_module.shutil.move

    def spying_move(src, dst):
        move_calls.append((src, dst))
        return real_move(src, dst)

    monkeypatch.setattr(libreoffice_module.shutil, "move", spying_move)

    converter = LibreOfficeConverter()
    converter.convert(input_path, output_path, ConversionOptions())

    assert len(move_calls) == 1
    assert move_calls[0][1] == str(output_path)


def test_convert_raises_conversion_failed_when_rename_fails(monkeypatch, tmp_path):
    # Regression: a locked destination (e.g. open in a PDF viewer) must
    # surface as a ProteusError, not a bare PermissionError.
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: _available())

    input_path = tmp_path / "in.docx"
    input_path.write_text("placeholder")
    output_path = tmp_path / "renamed.pdf"

    def fake_run_subprocess(cmd, **kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "in.pdf").write_bytes(b"%PDF-fake")

    monkeypatch.setattr(libreoffice_module, "run_subprocess", fake_run_subprocess)

    def raise_permission_error(src, dst):
        raise PermissionError("destination is open elsewhere")

    monkeypatch.setattr(libreoffice_module.shutil, "move", raise_permission_error)

    converter = LibreOfficeConverter()
    with pytest.raises(ConversionFailedError):
        converter.convert(input_path, output_path, ConversionOptions())
