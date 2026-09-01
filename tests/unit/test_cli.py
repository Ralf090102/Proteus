"""CLI smoke tests via Typer's CliRunner — exercises command wiring, not
conversion fidelity (that's the manual check / integration test)."""

from __future__ import annotations

from typer.testing import CliRunner

from proteus import cli as cli_module
from proteus.cli import app
from proteus.core.errors import ConversionFailedError

runner = CliRunner()


def test_list_formats_shows_all_registered_pairs():
    result = runner.invoke(app, ["list-formats"])
    assert result.exit_code == 0
    assert "docx" in result.stdout
    assert "pdf" in result.stdout
    assert "md" in result.stdout


def test_doctor_runs_successfully():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "docx -> pdf" in result.stdout
    assert "docx -> md" in result.stdout
    assert "md -> docx" in result.stdout
    assert "md -> pdf" in result.stdout
    assert "pdf -> docx" in result.stdout
    assert "pdf -> txt" in result.stdout


def test_convert_unregistered_pair_exits_nonzero(tmp_path):
    input_file = tmp_path / "in.txt"
    input_file.write_text("placeholder")
    result = runner.invoke(app, ["convert", str(input_file), "--to", "pdf"])
    assert result.exit_code == 1
    # Errors go to stderr (Unix convention) — check the combined stream.
    assert "txt" in result.output
    assert "pdf" in result.output


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


def test_install_context_menu_reports_installed_pairs(monkeypatch):
    monkeypatch.setattr(cli_module.context_menu, "install", lambda: ["docx -> pdf", "md -> pdf"])
    result = runner.invoke(app, ["install-context-menu"])
    assert result.exit_code == 0
    assert "docx -> pdf" in result.stdout
    assert "md -> pdf" in result.stdout


def test_install_context_menu_reports_missing_proteus_on_path_cleanly(monkeypatch):
    def raise_runtime_error():
        raise RuntimeError("proteus isn't on PATH. Run `uv tool install .` first.")

    monkeypatch.setattr(cli_module.context_menu, "install", raise_runtime_error)
    result = runner.invoke(app, ["install-context-menu"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "uv tool install" in result.output


def test_uninstall_context_menu_reports_removed_pairs(monkeypatch):
    monkeypatch.setattr(cli_module.context_menu, "uninstall", lambda: ["docx -> pdf"])
    result = runner.invoke(app, ["uninstall-context-menu"])
    assert result.exit_code == 0
    assert "docx -> pdf" in result.stdout


def test_uninstall_context_menu_reports_nothing_installed(monkeypatch):
    monkeypatch.setattr(cli_module.context_menu, "uninstall", lambda: [])
    result = runner.invoke(app, ["uninstall-context-menu"])
    assert result.exit_code == 0
    assert "No proteus context-menu entries" in result.stdout


def test_convert_from_context_menu_success_reveals_in_explorer_not_console(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli_module.subprocess, "Popen", lambda cmd: calls.append(cmd))

    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    output_path = tmp_path / "in.pdf"

    class _FakeConverter:
        def convert(self, input_path, out_path, options):
            from proteus.core.converter import ConversionResult

            output_path.write_bytes(b"%PDF-fake")
            return ConversionResult(output_path=output_path)

    monkeypatch.setattr(cli_module, "get_converter", lambda *a, **k: _FakeConverter())

    result = runner.invoke(
        app, ["convert", str(input_file), "--to", "pdf", "--from-context-menu"]
    )

    assert result.exit_code == 0
    assert result.output == ""  # no console output attempted in this mode
    assert len(calls) == 1
    assert calls[0][0] == "explorer"
    assert calls[0][1] == f"/select,{output_path}"


def test_convert_from_context_menu_failure_shows_message_box_not_console(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        cli_module.ctypes.windll.user32,
        "MessageBoxW",
        lambda *args: calls.append(args),
    )

    def raise_conversion_failed(*args, **kwargs):
        raise ConversionFailedError("boom")

    monkeypatch.setattr(cli_module, "get_converter", raise_conversion_failed)

    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")

    result = runner.invoke(
        app, ["convert", str(input_file), "--to", "pdf", "--from-context-menu"]
    )

    assert result.exit_code == 1
    assert result.output == ""  # no console output attempted in this mode
    assert len(calls) == 1
    assert "boom" in calls[0][1]
