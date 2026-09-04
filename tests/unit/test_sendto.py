"""Tests for windows/sendto.py's install()/uninstall(), mocking
subprocess.run so nothing ever shells out to a real PowerShell/COM call —
same tier of confidence as test_context_menu.py's fake winreg, adapted to
this module's different mechanism (shelled-out PowerShell instead of
winreg)."""

from __future__ import annotations

import subprocess

import pytest

from proteus.windows import sendto as sendto_module


@pytest.fixture
def fake_sendto_dir(monkeypatch, tmp_path):
    sendto_dir = tmp_path / "SendTo"
    monkeypatch.setattr(sendto_module, "SENDTO_DIR", sendto_dir)
    return sendto_dir


@pytest.fixture
def fake_proteus_exe(monkeypatch, tmp_path):
    exe_path = tmp_path / "proteus-gui.exe"
    monkeypatch.setattr(sendto_module, "resolve_proteus_gui_exe_path", lambda: exe_path)
    return exe_path


@pytest.fixture
def fake_subprocess_run(monkeypatch):
    """Records every subprocess.run() call's script (the -Command arg)
    instead of actually launching PowerShell; always reports success
    unless a test overrides the return code via calls[i].returncode."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sendto_module.subprocess, "run", fake_run)
    return calls


def test_install_creates_eight_shortcuts(
    fake_sendto_dir, fake_proteus_exe, fake_subprocess_run
):
    installed = sendto_module.install()

    assert len(installed) == 8
    assert len(fake_subprocess_run) == 8
    for label in sendto_module.TARGET_LABELS:
        assert label in installed
        assert f"{label} (Replace Originals)" in installed


def test_install_creates_sendto_dir_if_missing(
    fake_sendto_dir, fake_proteus_exe, fake_subprocess_run
):
    assert not fake_sendto_dir.exists()
    sendto_module.install()
    assert fake_sendto_dir.exists()


def test_install_script_references_correct_lnk_path_and_exe(
    fake_sendto_dir, fake_proteus_exe, fake_subprocess_run
):
    sendto_module.install()

    scripts = [cmd[-1] for cmd in fake_subprocess_run]
    plain_pdf_script = next(s for s in scripts if "Merge PDF.lnk" in s and "Replace" not in s)
    assert str(fake_proteus_exe) in plain_pdf_script
    assert "merge --from-context-menu" in plain_pdf_script
    assert "--replace-source" not in plain_pdf_script


def test_install_replace_variant_carries_replace_source_flag(
    fake_sendto_dir, fake_proteus_exe, fake_subprocess_run
):
    sendto_module.install()

    scripts = [cmd[-1] for cmd in fake_subprocess_run]
    replace_script = next(s for s in scripts if "Merge PDF (Replace Originals).lnk" in s)
    assert "--replace-source" in replace_script
    assert "merge --from-context-menu" in replace_script


def test_install_propagates_when_proteus_gui_not_found(fake_sendto_dir, monkeypatch):
    def raise_not_found():
        raise RuntimeError("proteus-gui isn't on PATH.")

    monkeypatch.setattr(sendto_module, "resolve_proteus_gui_exe_path", raise_not_found)

    with pytest.raises(RuntimeError, match="proteus-gui"):
        sendto_module.install()


def test_run_powershell_raises_oserror_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(sendto_module.subprocess, "run", fake_run)

    with pytest.raises(OSError, match="boom"):
        sendto_module._run_powershell("some script")


def test_uninstall_removes_only_files_that_actually_exist(fake_sendto_dir):
    fake_sendto_dir.mkdir(parents=True)
    (fake_sendto_dir / "Merge PDF.lnk").write_text("placeholder")
    (fake_sendto_dir / "Images to PDF (Replace Originals).lnk").write_text("placeholder")

    removed = sendto_module.uninstall()

    assert sorted(removed) == sorted(
        ["Merge PDF", "Images to PDF (Replace Originals)"]
    )
    assert not (fake_sendto_dir / "Merge PDF.lnk").exists()
    assert not (fake_sendto_dir / "Images to PDF (Replace Originals).lnk").exists()


def test_uninstall_on_clean_state_is_a_noop_not_an_error(fake_sendto_dir):
    fake_sendto_dir.mkdir(parents=True)
    removed = sendto_module.uninstall()
    assert removed == []


def test_uninstall_when_sendto_dir_does_not_exist_is_a_noop_not_an_error(fake_sendto_dir):
    assert not fake_sendto_dir.exists()
    removed = sendto_module.uninstall()
    assert removed == []


def test_ps_escape_escapes_single_quotes():
    assert sendto_module._ps_escape("O'Brien's file") == "O''Brien''s file"


def test_shortcut_names_covers_every_target_and_replace_variant():
    names = sendto_module._shortcut_names()
    assert len(names) == 8
    for label in sendto_module.TARGET_LABELS:
        assert label in names
        assert f"{label}{sendto_module.REPLACE_SUFFIX}" in names
