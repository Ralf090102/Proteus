"""Windows Explorer right-click context menu — winreg install/uninstall.

Everything nests under one "Proteus" cascading submenu per source
extension, using the documented static-cascading-menu mechanism (no
COM/DLL needed): a parent key with MUIVerb="Proteus" and SubCommands=""
(the empty string is what tells Explorer "render this key's own \\shell
children as a submenu" instead of treating the key as a leaf command).

Key shape, derived from CONVERTER_REGISTRY:
  HKCU\\Software\\Classes\\SystemFileAssociations\\.{from_ext}
    \\shell\\proteus_menu                    (parent: MUIVerb, SubCommands)
      \\shell\\proteus_convert_to_{to_ext}   (one per registered pair for that from_ext)
        \\command

HKCU-only — no admin rights. Every key this installs is proteus_-prefixed
so uninstall() removes exactly what install() created and nothing else.
"""

from __future__ import annotations

import shutil
import winreg
from pathlib import Path

from proteus.core.registry import CONVERTER_REGISTRY

MENU_KEY_NAME = "proteus_menu"
MENU_DISPLAY_NAME = "Proteus"
VERB_PREFIX = "proteus_convert_to_"
CLASSES_ROOT = winreg.HKEY_CURRENT_USER


def _verb_name(to_ext: str) -> str:
    return f"{VERB_PREFIX}{to_ext}"


def _menu_key_path(from_ext: str) -> str:
    return rf"Software\Classes\SystemFileAssociations\.{from_ext}\shell\{MENU_KEY_NAME}"


def _proteus_exe_path() -> Path:
    """Resolve the installed `proteus` CLI's own absolute exe path.

    Explorer launches the registered command with no working directory
    or project-venv context of its own, so this needs a stable, global
    path — exactly what `uv tool install .` provides.
    """
    which_result = shutil.which("proteus")
    if which_result is None:
        raise RuntimeError(
            "proteus isn't on PATH. Run `uv tool install .` first so the context "
            "menu has a stable exe path to point at."
        )
    return Path(which_result).resolve()


def install() -> list[str]:
    """Install one "Proteus" cascading submenu per source extension, with
    one item inside it per registered conversion pair for that extension.

    Returns the "from -> to" pairs installed.
    """
    exe_path = _proteus_exe_path()

    from_exts = sorted({from_ext for from_ext, _ in CONVERTER_REGISTRY})
    for from_ext in from_exts:
        _install_menu(from_ext)

    installed = []
    for from_ext, to_ext in sorted(CONVERTER_REGISTRY.keys()):
        _install_verb(exe_path, from_ext, to_ext)
        installed.append(f"{from_ext} -> {to_ext}")
    return installed


def _install_menu(from_ext: str) -> None:
    with winreg.CreateKeyEx(CLASSES_ROOT, _menu_key_path(from_ext)) as key:
        winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, MENU_DISPLAY_NAME)
        # Empty string is the documented signal for a static cascading
        # submenu — Explorer renders this key's \shell children as the
        # submenu instead of expecting a COM handler.
        winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "")


def _install_verb(exe_path: Path, from_ext: str, to_ext: str) -> None:
    verb = _verb_name(to_ext)
    shell_key_path = rf"{_menu_key_path(from_ext)}\shell\{verb}"
    command_key_path = rf"{shell_key_path}\command"

    with winreg.CreateKeyEx(CLASSES_ROOT, shell_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"Convert to {to_ext.upper()}")

    command = f'"{exe_path}" convert "%1" --to {to_ext} --from-context-menu'
    with winreg.CreateKeyEx(CLASSES_ROOT, command_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def uninstall() -> list[str]:
    """Remove every proteus-installed "Proteus" submenu (and everything
    nested under it).

    Safe to call even if nothing (or only some extensions) were
    installed — missing keys are skipped, not an error. Returns the
    "from -> to" pairs actually removed.
    """
    removed = []
    from_exts = sorted({from_ext for from_ext, _ in CONVERTER_REGISTRY})
    for from_ext in from_exts:
        pairs_for_ext = sorted(
            to_ext for f_ext, to_ext in CONVERTER_REGISTRY if f_ext == from_ext
        )
        if _delete_key_tree(CLASSES_ROOT, _menu_key_path(from_ext)):
            removed.extend(f"{from_ext} -> {to_ext}" for to_ext in pairs_for_ext)
    return removed


def _delete_key_tree(root: int, path: str) -> bool:
    """Recursively delete a registry key and its subkeys — winreg has no
    built-in recursive delete. EnumKey(key, 0) is called repeatedly
    (rather than iterating an index) because each recursive delete of the
    current index-0 subkey shifts the next one into index 0.

    Returns True if the key existed and was removed, False if it didn't
    exist to begin with (not an error).
    """
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_key_tree(root, f"{path}\\{subkey_name}")
        winreg.DeleteKey(root, path)
        return True
    except FileNotFoundError:
        return False
