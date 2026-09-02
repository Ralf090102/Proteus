"""CLI smoke tests via Typer's CliRunner — exercises command wiring, not
conversion fidelity (that's the manual check / integration test)."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest
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


def test_doctor_shows_details_column_and_bundled_note_for_library_backed_pairs():
    # pdf->docx / pdf->txt wrap hard Python dependencies with no external
    # tool at all — doctor must say so rather than leaving Details blank.
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    output_no_wrap = result.stdout.replace("\n", "")
    assert "Details" in output_no_wrap
    assert "bundled" in output_no_wrap


def test_doctor_shows_resolved_path_for_an_available_tool_backed_converter(monkeypatch):
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.core.dependencies import AvailabilityStatus

    resolved = Path("known-location") / "soffice"
    monkeypatch.setattr(
        libreoffice_module,
        "find_tool",
        lambda *a, **k: AvailabilityStatus(True, resolved, "known-location"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    # Table cells can line-wrap under CliRunner's default width — collapse
    # newlines before checking for the (long-ish) path substring.
    assert str(resolved) in result.stdout.replace("\n", "")


def test_doctor_shows_install_link_when_a_tool_backed_converter_is_missing(monkeypatch):
    # Regression: a long install URL truncates with "…" if squeezed into a
    # narrow table cell (confirmed under CliRunner's 80-col default) — it
    # must appear in full, in the separate list doctor() prints below the
    # table, not inside the table itself.
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.core.dependencies import AvailabilityStatus

    monkeypatch.setattr(
        libreoffice_module,
        "find_tool",
        lambda *a, **k: AvailabilityStatus(False, None, "not-found"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    output_no_wrap = result.stdout.replace("\n", "")
    assert "soffice: not found" in output_no_wrap
    assert "Install missing tools" in output_no_wrap
    assert "https://www.libreoffice.org/download/download-libreoffice/" in output_no_wrap


def test_doctor_lists_each_missing_tool_only_once_across_multiple_pairs(monkeypatch):
    # soffice backs both docx->pdf and (as one half of) the md->pdf chain —
    # the install-link list must not repeat it.
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.core.dependencies import AvailabilityStatus

    monkeypatch.setattr(
        libreoffice_module,
        "find_tool",
        lambda *a, **k: AvailabilityStatus(False, None, "not-found"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert result.stdout.count("libreoffice.org") == 1


def test_doctor_chain_pair_details_surfaces_both_underlying_tools(monkeypatch):
    # md->pdf is a ChainConverter over Pandoc + LibreOffice — doctor's
    # Details column must show both, not collapse to one bool.
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.converters import pandoc as pandoc_module
    from proteus.core.dependencies import AvailabilityStatus

    monkeypatch.setattr(
        pandoc_module,
        "find_tool",
        lambda *a, **k: AvailabilityStatus(True, Path("/usr/bin/pandoc"), "path"),
    )
    monkeypatch.setattr(
        libreoffice_module,
        "find_tool",
        lambda *a, **k: AvailabilityStatus(False, None, "not-found"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    output_no_wrap = result.stdout.replace("\n", "")
    assert "pandoc:" in output_no_wrap
    assert "soffice: not found" in output_no_wrap


def test_doctor_prints_no_install_links_section_when_everything_available(monkeypatch):
    import sys
    import types

    from proteus.converters import libreoffice as libreoffice_module
    from proteus.converters import pandoc as pandoc_module
    from proteus.core.dependencies import AvailabilityStatus

    available = AvailabilityStatus(True, Path("/usr/bin/tool"), "path")
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: available)
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: available)

    # Pillow (the `images` extra, backing the png/jpg/webp pairs) may or
    # may not actually be installed in the environment running this test —
    # stub it present so "everything available" genuinely means everything,
    # independent of whether the optional extra happens to be installed.
    fake_pil = types.ModuleType("PIL")
    fake_pil.__file__ = "C:/fake-site-packages/PIL/__init__.py"
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Install missing tools" not in result.stdout


def test_install_deps_reports_nothing_missing_when_all_available(monkeypatch):
    monkeypatch.setattr(cli_module, "_collect_missing_tools", lambda: {})

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 0
    assert "already installed" in result.stdout


def test_install_deps_installs_missing_tools_via_winget(monkeypatch):
    monkeypatch.setattr(cli_module, "_collect_missing_tools", lambda: {"soffice": "tool"})
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "C:/winget.exe")
    monkeypatch.setattr(cli_module, "_install_via_winget", lambda package_id: True)

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 0
    assert "Installed 1 tool(s)" in result.stdout
    assert "TheDocumentFoundation.LibreOffice" in result.stdout


def test_install_deps_reports_failure_when_winget_install_fails(monkeypatch):
    monkeypatch.setattr(cli_module, "_collect_missing_tools", lambda: {"soffice": "tool"})
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "C:/winget.exe")
    monkeypatch.setattr(cli_module, "_install_via_winget", lambda package_id: False)

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 1
    assert "0 installed, 1 failed" in result.stdout


def test_install_deps_errors_when_winget_missing(monkeypatch):
    monkeypatch.setattr(cli_module, "_collect_missing_tools", lambda: {"soffice": "tool"})
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: None)

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 1
    assert "winget was not found" in result.output
    assert "libreoffice.org" in result.output


def test_install_deps_lists_manual_install_for_tool_without_winget_package(monkeypatch):
    monkeypatch.setattr(cli_module, "_collect_missing_tools", lambda: {"some-tool": "tool"})

    result = runner.invoke(app, ["install-deps"])

    # Nothing installable via winget at all, so the winget-presence check
    # is skipped entirely and this falls straight to the manual-only list.
    assert result.exit_code == 1
    assert "No winget package for" in result.stdout
    assert "some-tool" in result.stdout


def test_install_deps_reports_missing_extra_without_attempting_winget(monkeypatch):
    monkeypatch.setattr(cli_module, "_collect_missing_tools", lambda: {"pillow": "extra"})

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 0
    assert "Optional extras not installed" in result.stdout
    assert "uv tool install .[images]" in result.stdout


def test_install_deps_exits_nonzero_on_partial_failure(monkeypatch):
    # Regression: installing 2 tools where one succeeds and one fails must
    # not exit 0 just because *something* succeeded — a caller scripting
    # `install-deps && doctor` needs partial failure to read as failure.
    monkeypatch.setattr(
        cli_module, "_collect_missing_tools", lambda: {"soffice": "tool", "pandoc": "tool"}
    )
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "C:/winget.exe")
    results = {
        cli_module.WINGET_PACKAGE_IDS["soffice"]: True,
        cli_module.WINGET_PACKAGE_IDS["pandoc"]: False,
    }
    monkeypatch.setattr(cli_module, "_install_via_winget", lambda package_id: results[package_id])

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 1
    assert "1 installed, 1 failed" in result.stdout


def test_collect_missing_tools_raises_on_unrecognized_kind(monkeypatch):
    # A ToolCheck.kind that's neither "tool" nor "extra" must fail loudly
    # here (the single choke point doctor()/install_deps() both use)
    # rather than silently landing in neither bucket downstream.
    from proteus.core.converter import ToolCheck
    from proteus.core.dependencies import AvailabilityStatus

    class _BadConverter:
        def tool_checks(self):
            return (ToolCheck("mystery", AvailabilityStatus(False, None, "not-found"), "bogus"),)

    monkeypatch.setattr(cli_module, "CONVERTER_REGISTRY", {("x", "y"): _BadConverter})

    with pytest.raises(RuntimeError, match="unrecognized ToolCheck kind"):
        cli_module._collect_missing_tools()


def test_doctor_does_not_hint_install_deps_when_only_extra_missing(monkeypatch):
    import sys

    from proteus.converters import libreoffice as libreoffice_module
    from proteus.converters import pandoc as pandoc_module
    from proteus.core.dependencies import AvailabilityStatus

    available = AvailabilityStatus(True, Path("/usr/bin/tool"), "path")
    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: available)
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: available)
    monkeypatch.setitem(sys.modules, "PIL", None)  # only pillow (an extra) is missing

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "optional extra not installed" in result.output  # extra IS reported
    assert "proteus install-deps" not in result.output.replace("\n", "")  # but no winget hint


def test_install_deps_reports_both_missing_tool_and_missing_extra(monkeypatch):
    monkeypatch.setattr(
        cli_module, "_collect_missing_tools", lambda: {"soffice": "tool", "pillow": "extra"}
    )
    monkeypatch.setattr(cli_module.shutil, "which", lambda name: "C:/winget.exe")
    monkeypatch.setattr(cli_module, "_install_via_winget", lambda package_id: True)

    result = runner.invoke(app, ["install-deps"])

    assert result.exit_code == 0
    assert "Installed 1 tool(s)" in result.stdout
    assert "Optional extras not installed" in result.stdout
    assert "pillow" in result.stdout


def test_doctor_hints_at_install_deps_when_a_winget_installable_tool_is_missing(monkeypatch):
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.core.dependencies import AvailabilityStatus

    monkeypatch.setattr(
        libreoffice_module,
        "find_tool",
        lambda *a, **k: AvailabilityStatus(False, None, "not-found"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "proteus install-deps" in result.stdout.replace("\n", "")


def test_install_via_winget_returns_true_on_success(monkeypatch):
    captured_cmd = {}

    class _FakeCompletedProcess:
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured_cmd["cmd"] = cmd
        return _FakeCompletedProcess()

    monkeypatch.setattr(cli_module.subprocess, "run", fake_run)

    assert cli_module._install_via_winget("Some.Package") is True
    assert captured_cmd["cmd"][:3] == ["winget", "install", "--id"]
    assert "Some.Package" in captured_cmd["cmd"]
    assert "--silent" in captured_cmd["cmd"]


def test_install_via_winget_returns_false_on_nonzero_exit(monkeypatch):
    class _FakeCompletedProcess:
        returncode = 1

    monkeypatch.setattr(cli_module.subprocess, "run", lambda cmd, **kwargs: _FakeCompletedProcess())

    assert cli_module._install_via_winget("Some.Package") is False


def test_doctor_shows_optional_extra_not_installed_not_not_found(monkeypatch):
    # Regression for the roadmap's explicit ask: a missing optional Python
    # extra (Pillow) must read differently from a missing external tool —
    # there's no download-page link for a pip extra, the fix is a `uv
    # tool install` command instead.
    import sys

    monkeypatch.setitem(sys.modules, "PIL", None)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    # Table cells can line-wrap under CliRunner's narrow default width
    # (same caveat as the other doctor table-content tests above), so
    # check the footer's install-instructions list — always printed as
    # one unwrapped line — rather than the table's Details cell directly.
    assert "optional extra not installed" in result.output
    assert "uv tool install .[images]" in result.output
    assert "pillow: not found" not in result.output.replace("\n", "")


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


def test_install_context_menu_reports_os_error_cleanly(monkeypatch):
    # Regression: a winreg failure other than the "not on PATH"
    # RuntimeError (e.g. access denied) used to escape as a raw
    # unhandled traceback instead of a clean CLI error.
    def raise_os_error():
        raise OSError("Access is denied")

    monkeypatch.setattr(cli_module.context_menu, "install", raise_os_error)
    result = runner.invoke(app, ["install-context-menu"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Access is denied" in result.output


def test_uninstall_context_menu_reports_os_error_cleanly(monkeypatch):
    # Regression: uninstall-context-menu had no error handling at all —
    # any winreg failure crashed with a raw traceback.
    def raise_os_error():
        raise OSError("Access is denied")

    monkeypatch.setattr(cli_module.context_menu, "uninstall", raise_os_error)
    result = runner.invoke(app, ["uninstall-context-menu"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Access is denied" in result.output


def test_convert_from_context_menu_success_is_fully_silent(monkeypatch, tmp_path):
    # Regression: a right-click conversion used to always pop open a new
    # Explorer window on success — it must now do nothing visible at all.
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
    assert result.output == ""  # no console output, no Explorer window either
    assert output_path.exists()
    assert input_file.exists()  # source untouched without --replace-source


def test_convert_replace_source_deletes_original_on_success(monkeypatch, tmp_path):
    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    output_path = tmp_path / "in.pdf"

    class _FakeConverter:
        def convert(self, input_path, out_path, options):
            from proteus.core.converter import ConversionResult

            output_path.write_bytes(b"%PDF-fake")
            return ConversionResult(output_path=output_path)

    monkeypatch.setattr(cli_module, "get_converter", lambda *a, **k: _FakeConverter())

    result = runner.invoke(app, ["convert", str(input_file), "--to", "pdf", "--replace-source"])

    assert result.exit_code == 0
    assert output_path.exists()
    assert not input_file.exists()


def test_convert_replace_source_not_applied_when_conversion_fails(monkeypatch, tmp_path):
    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")

    def raise_conversion_failed(*args, **kwargs):
        raise ConversionFailedError("boom")

    monkeypatch.setattr(cli_module, "get_converter", raise_conversion_failed)

    result = runner.invoke(app, ["convert", str(input_file), "--to", "pdf", "--replace-source"])

    assert result.exit_code == 1
    assert input_file.exists()


def test_convert_replace_source_delete_failure_warns_but_does_not_fail_command(
    monkeypatch, tmp_path
):
    # A locked/in-use source file is a real possibility — the conversion
    # itself already succeeded, so this must be a warning, not a failure.
    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    output_path = tmp_path / "in.pdf"

    class _FakeConverter:
        def convert(self, input_path, out_path, options):
            from proteus.core.converter import ConversionResult

            output_path.write_bytes(b"%PDF-fake")
            return ConversionResult(output_path=output_path)

    monkeypatch.setattr(cli_module, "get_converter", lambda *a, **k: _FakeConverter())
    monkeypatch.setattr(
        cli_module.Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("in use"))
    )

    result = runner.invoke(app, ["convert", str(input_file), "--to", "pdf", "--replace-source"])

    assert result.exit_code == 0
    assert "Warning" in result.output
    assert "in use" in result.output


@pytest.mark.skipif(sys.platform != "win32", reason="real file-lock semantics are Windows-specific")
def test_convert_replace_source_delete_failure_with_a_real_locked_file(monkeypatch, tmp_path):
    # Regression for the two mocked-OSError tests above (both monkeypatch
    # Path.unlink to unconditionally throw): reproduce a genuine OS-level
    # lock instead. dwShareMode=0 denies all sharing, including delete —
    # unlike plain open()/os.open(), which normally allow delete-while-
    # open on Windows — so this is real "file open in another program"
    # semantics, not a synthetic mock.
    from ctypes import wintypes

    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    output_path = tmp_path / "in.pdf"

    class _FakeConverter:
        def convert(self, input_path, out_path, options):
            from proteus.core.converter import ConversionResult

            output_path.write_bytes(b"%PDF-fake")
            return ConversionResult(output_path=output_path)

    monkeypatch.setattr(cli_module, "get_converter", lambda *a, **k: _FakeConverter())

    create_file_w = ctypes.windll.kernel32.CreateFileW
    create_file_w.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file_w.restype = wintypes.HANDLE
    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]

    generic_read = 0x80000000
    open_existing = 3
    invalid_handle_value = wintypes.HANDLE(-1).value

    handle = create_file_w(str(input_file), generic_read, 0, None, open_existing, 0, None)
    assert handle != invalid_handle_value, "failed to open the test file with no sharing"

    try:
        result = runner.invoke(
            app, ["convert", str(input_file), "--to", "pdf", "--replace-source"]
        )

        assert result.exit_code == 0
        assert "Warning" in result.output
        assert input_file.exists()  # the real lock genuinely prevented deletion
    finally:
        close_handle(handle)


def test_convert_replace_source_delete_failure_from_context_menu_shows_message_box(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(
        cli_module.ctypes.windll.user32,
        "MessageBoxW",
        lambda *args: calls.append(args),
    )

    input_file = tmp_path / "in.docx"
    input_file.write_text("placeholder")
    output_path = tmp_path / "in.pdf"

    class _FakeConverter:
        def convert(self, input_path, out_path, options):
            from proteus.core.converter import ConversionResult

            output_path.write_bytes(b"%PDF-fake")
            return ConversionResult(output_path=output_path)

    monkeypatch.setattr(cli_module, "get_converter", lambda *a, **k: _FakeConverter())
    monkeypatch.setattr(
        cli_module.Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("in use"))
    )

    result = runner.invoke(
        app,
        ["convert", str(input_file), "--to", "pdf", "--replace-source", "--from-context-menu"],
    )

    assert result.exit_code == 0
    assert result.output == ""
    assert len(calls) == 1
    assert "in use" in calls[0][1]


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


def test_main_shows_message_box_for_unexpected_error_from_context_menu(monkeypatch):
    # A windowed proteus-gui process (see main()'s docstring) has no
    # console to show a traceback in — anything that escapes app()'s own
    # ProteusError handling during --from-context-menu must still surface
    # somewhere, not vanish silently.
    calls = []
    monkeypatch.setattr(
        cli_module.ctypes.windll.user32,
        "MessageBoxW",
        lambda *args: calls.append(args),
    )

    def raise_unexpected(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(cli_module, "app", raise_unexpected)
    monkeypatch.setattr(
        cli_module.sys, "argv", ["proteus-gui", "convert", "x", "--from-context-menu"]
    )

    with pytest.raises(SystemExit):
        cli_module.main()

    assert len(calls) == 1
    assert "boom" in calls[0][1]


def test_main_reraises_unexpected_error_when_not_from_context_menu(monkeypatch):
    def raise_unexpected(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(cli_module, "app", raise_unexpected)
    monkeypatch.setattr(cli_module.sys, "argv", ["proteus", "convert", "x"])

    with pytest.raises(ValueError, match="boom"):
        cli_module.main()
