"""CLI smoke tests via Typer's CliRunner — exercises command wiring, not
conversion fidelity (that's the manual check / integration test)."""

from __future__ import annotations

from typer.testing import CliRunner

from proteus import cli as cli_module
from proteus.cli import app
from proteus.core.errors import ConversionFailedError

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


def test_convert_empty_to_ext_exits_cleanly_instead_of_crashing(tmp_path):
    # Regression: --to "" used to reach Path.with_suffix(".") and raise an
    # unhandled ValueError instead of a clean CLI error.
    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    result = runner.invoke(app, ["convert", str(input_file), "--to", ""])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Invalid target format" in result.output


def test_convert_error_message_with_bracket_like_text_does_not_crash_rich(tmp_path):
    # Regression: an unregistered pair whose extension contains rich
    # markup-like text must not raise rich.errors.MarkupError while
    # trying to report the original error.
    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    result = runner.invoke(app, ["convert", str(input_file), "--to", "pdf[/bold]"])
    assert isinstance(result.exception, SystemExit)


def test_convert_reports_proteus_error_with_bracket_like_text_without_crashing(
    monkeypatch, tmp_path
):
    # Regression: ConversionFailedError can embed raw subprocess
    # stdout/stderr verbatim — if that text happens to contain something
    # shaped like a rich closing tag (e.g. "[/foo]"), reporting the error
    # must not itself raise rich.errors.MarkupError.
    def raise_with_markup_like_message(*args, **kwargs):
        raise ConversionFailedError("soffice failed\nstderr: unexpected [/nope] token")

    monkeypatch.setattr(cli_module, "get_converter", raise_with_markup_like_message)

    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    result = runner.invoke(app, ["convert", str(input_file), "--to", "pdf"])

    assert isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "[/nope]" in result.output
