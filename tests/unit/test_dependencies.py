"""Tests for find_tool()'s env/which/known-location/not-found precedence."""

from __future__ import annotations

from pathlib import Path

from proteus.core import dependencies as dependencies_module
from proteus.core.dependencies import find_tool


def test_env_override_wins_when_it_points_at_a_real_file(monkeypatch, tmp_path):
    fake_binary = tmp_path / "custom-soffice.exe"
    fake_binary.write_text("placeholder")
    monkeypatch.setenv("PROTEUS_TEST_TOOL_PATH", str(fake_binary))
    monkeypatch.setattr(dependencies_module.shutil, "which", lambda _: None)

    status = find_tool("sometool", env_var="PROTEUS_TEST_TOOL_PATH")

    assert status.available is True
    assert status.path == fake_binary
    assert status.source == "env"


def test_env_override_ignored_when_it_points_at_a_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTEUS_TEST_TOOL_PATH", str(tmp_path / "does-not-exist.exe"))
    monkeypatch.setattr(dependencies_module.shutil, "which", lambda _: "/usr/bin/sometool")

    status = find_tool("sometool", env_var="PROTEUS_TEST_TOOL_PATH")

    # Falls through to the next source rather than trusting a stale/wrong override.
    assert status.available is True
    assert status.source == "path"


def test_falls_back_to_which_when_no_env_var_given(monkeypatch):
    monkeypatch.setattr(dependencies_module.shutil, "which", lambda _: "/usr/bin/sometool")

    status = find_tool("sometool")

    assert status.available is True
    assert status.path == Path("/usr/bin/sometool")
    assert status.source == "path"


def test_falls_back_to_known_install_path(monkeypatch, tmp_path):
    known_path = tmp_path / "known" / "sometool.exe"
    known_path.parent.mkdir()
    known_path.write_text("placeholder")
    monkeypatch.setitem(dependencies_module.KNOWN_INSTALL_PATHS, "sometool", (known_path,))
    monkeypatch.setattr(dependencies_module.shutil, "which", lambda _: None)

    status = find_tool("sometool")

    assert status.available is True
    assert status.path == known_path
    assert status.source == "known-location"


def test_not_found_when_no_source_has_it(monkeypatch):
    monkeypatch.setattr(dependencies_module.shutil, "which", lambda _: None)
    monkeypatch.setitem(dependencies_module.KNOWN_INSTALL_PATHS, "sometool", ())

    status = find_tool("sometool")

    assert status.available is False
    assert status.path is None
    assert status.source == "not-found"
