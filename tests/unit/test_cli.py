"""CLI smoke tests via Typer's CliRunner — exercises command wiring, not
conversion fidelity (that's the manual check / integration test)."""

from __future__ import annotations

from typer.testing import CliRunner

from proteus.cli import app

runner = CliRunner()


def test_list_formats_shows_docx_to_pdf():
    result = runner.invoke(app, ["list-formats"])
    assert result.exit_code == 0
    assert "docx" in result.stdout
    assert "pdf" in result.stdout


def test_doctor_runs_successfully():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "docx -> pdf" in result.stdout


def test_convert_unregistered_pair_exits_nonzero(tmp_path):
    input_file = tmp_path / "in.pdf"
    input_file.write_text("placeholder")
    result = runner.invoke(app, ["convert", str(input_file), "--to", "docx"])
    assert result.exit_code == 1
    # Errors go to stderr (Unix convention) — check the combined stream.
    assert "pdf" in result.output
    assert "docx" in result.output


def test_convert_missing_input_file_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["convert", str(tmp_path / "does-not-exist.docx"), "--to", "pdf"])
    assert result.exit_code != 0
