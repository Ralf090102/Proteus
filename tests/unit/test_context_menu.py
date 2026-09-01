"""Tests for windows/context_menu.py's install()/uninstall(), using an
in-memory fake winreg so nothing ever touches the real registry.

Verifies the nested "Proteus" cascading-submenu structure:
  .{from_ext}\\shell\\proteus_menu                                  (parent: MUIVerb/SubCommands)
    \\shell\\proteus_convert_to_{to_ext}                              (one per registered pair)
      \\command
"""

from __future__ import annotations

import pytest

from proteus.core.registry import CONVERTER_REGISTRY
from proteus.windows import context_menu as context_menu_module


class _FakeKeyHandle:
    def __init__(self, root, path):
        self.root = root
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeWinreg:
    """In-memory stand-in for the subset of winreg's API context_menu.py
    uses — a nested dict keyed by (root, path), backed by string keys so
    EnumKey can walk "subkeys" via prefix matching."""

    HKEY_CURRENT_USER = "HKEY_CURRENT_USER"
    KEY_ALL_ACCESS = 0xF003F
    REG_SZ = 1

    def __init__(self):
        self.keys: dict[tuple, dict] = {}

    def CreateKeyEx(self, root, path, *args, **kwargs):
        # Real winreg.CreateKeyEx creates every ancestor segment along the
        # path too, not just the leaf — mirror that so EnumKey/DeleteKey
        # can walk intermediate segments (e.g. "...\proteus_menu\shell")
        # that were never CreateKeyEx'd directly, only implied by a
        # deeper descendant. Without this, _delete_key_tree's recursive
        # walk "discovers" a phantom child that OpenKey can't find and
        # DeleteKey never actually removes, looping forever.
        parts = path.split("\\")
        for i in range(1, len(parts) + 1):
            ancestor_path = "\\".join(parts[:i])
            self.keys.setdefault((root, ancestor_path), {"values": {}})
        return _FakeKeyHandle(root, path)

    def OpenKey(self, root, path, *args, **kwargs):
        if (root, path) not in self.keys:
            raise FileNotFoundError(path)
        return _FakeKeyHandle(root, path)

    def SetValueEx(self, key, name, reserved, type_, value):
        self.keys[(key.root, key.path)]["values"][name] = value

    def EnumKey(self, key, index):
        prefix = key.path + "\\"
        children = sorted(
            {
                p[len(prefix) :].split("\\", 1)[0]
                for (r, p) in self.keys
                if r == key.root and p.startswith(prefix)
            }
        )
        if index >= len(children):
            raise OSError("no more subkeys")
        return children[index]

    def DeleteKey(self, root, path):
        if (root, path) not in self.keys:
            raise FileNotFoundError(path)
        del self.keys[(root, path)]


@pytest.fixture
def fake_winreg(monkeypatch):
    fake = _FakeWinreg()
    monkeypatch.setattr(context_menu_module, "winreg", fake)
    monkeypatch.setattr(context_menu_module, "CLASSES_ROOT", fake.HKEY_CURRENT_USER)
    return fake


@pytest.fixture
def fake_proteus_exe(monkeypatch, tmp_path):
    exe_path = tmp_path / "proteus.exe"
    exe_path.write_text("placeholder")
    monkeypatch.setattr(context_menu_module.shutil, "which", lambda _: str(exe_path))
    return exe_path


def test_proteus_exe_path_raises_when_not_on_path(monkeypatch):
    monkeypatch.setattr(context_menu_module.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="uv tool install"):
        context_menu_module._proteus_exe_path()


def test_install_creates_a_parent_menu_key_per_source_extension(fake_winreg, fake_proteus_exe):
    context_menu_module.install()

    from_exts = {from_ext for from_ext, _ in CONVERTER_REGISTRY}
    for from_ext in from_exts:
        menu_path = f"Software\\Classes\\SystemFileAssociations\\.{from_ext}\\shell\\proteus_menu"
        entry = fake_winreg.keys[(fake_winreg.HKEY_CURRENT_USER, menu_path)]
        assert entry["values"]["MUIVerb"] == "Proteus"
        assert entry["values"]["SubCommands"] == ""


def test_install_nests_a_verb_for_every_registered_pair_under_its_menu(
    fake_winreg, fake_proteus_exe
):
    installed = context_menu_module.install()

    assert len(installed) == len(CONVERTER_REGISTRY)
    for from_ext, to_ext in CONVERTER_REGISTRY:
        assert f"{from_ext} -> {to_ext}" in installed

        shell_path = (
            f"Software\\Classes\\SystemFileAssociations\\.{from_ext}"
            f"\\shell\\proteus_menu\\shell\\proteus_convert_to_{to_ext}"
        )
        command_path = f"{shell_path}\\command"

        assert (fake_winreg.HKEY_CURRENT_USER, shell_path) in fake_winreg.keys
        assert (fake_winreg.HKEY_CURRENT_USER, command_path) in fake_winreg.keys

        command_value = fake_winreg.keys[(fake_winreg.HKEY_CURRENT_USER, command_path)][
            "values"
        ][""]
        assert str(fake_proteus_exe) in command_value
        assert f"--to {to_ext}" in command_value
        assert "--from-context-menu" in command_value


def test_uninstall_after_install_leaves_no_proteus_keys(fake_winreg, fake_proteus_exe):
    context_menu_module.install()
    removed = context_menu_module.uninstall()

    assert len(removed) == len(CONVERTER_REGISTRY)
    # Ancestor keys legitimately persist (e.g. "...\SystemFileAssociations",
    # "...\.docx\shell" — other, non-Proteus shell verbs might live there
    # too) — only the proteus_-prefixed subtree should be gone.
    remaining_proteus_keys = [
        path for (_root, path) in fake_winreg.keys if "proteus_" in path
    ]
    assert remaining_proteus_keys == []


def test_uninstall_on_clean_state_is_a_noop_not_an_error(fake_winreg):
    removed = context_menu_module.uninstall()
    assert removed == []
