"""Windows Explorer right-click context menu — winreg install/uninstall.

Static, per-pair verbs under
HKCU\\Software\\Classes\\SystemFileAssociations\\.{ext}\\shell\\proteus_convert_to_{to_ext},
derived from CONVERTER_REGISTRY. HKCU-only — no admin rights, no COM/DLL
registration. Every key this installs is proteus_-prefixed so uninstall()
removes exactly what install() created and nothing else.
"""

from __future__ import annotations

import shutil
import winreg
from pathlib import Path

from proteus.core.registry import CONVERTER_REGISTRY

VERB_PREFIX = "proteus_convert_to_"
CLASSES_ROOT = winreg.HKEY_CURRENT_USER


def _verb_name(to_ext: str) -> str:
    return f"{VERB_PREFIX}{to_ext}"


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
    """Install one right-click verb per registered conversion pair.

    Returns the "from -> to" pairs installed.
    """
    exe_path = _proteus_exe_path()
    installed = []
    for from_ext, to_ext in sorted(CONVERTER_REGISTRY.keys()):
        _install_verb(exe_path, from_ext, to_ext)
        installed.append(f"{from_ext} -> {to_ext}")
    return installed


def _install_verb(exe_path: Path, from_ext: str, to_ext: str) -> None:
    verb = _verb_name(to_ext)
    shell_key_path = rf"Software\Classes\SystemFileAssociations\.{from_ext}\shell\{verb}"
    command_key_path = rf"{shell_key_path}\command"

    with winreg.CreateKeyEx(CLASSES_ROOT, shell_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"Convert to {to_ext.upper()}")

    command = f'"{exe_path}" convert "%1" --to {to_ext} --from-context-menu'
    with winreg.CreateKeyEx(CLASSES_ROOT, command_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def uninstall() -> list[str]:
    """Remove every proteus_-prefixed verb this installed.

    Safe to call even if nothing (or only some pairs) were installed —
    missing keys are skipped, not an error. Returns the "from -> to"
    pairs actually removed.
    """
    removed = []
    for from_ext, to_ext in sorted(CONVERTER_REGISTRY.keys()):
        verb = _verb_name(to_ext)
        shell_key_path = rf"Software\Classes\SystemFileAssociations\.{from_ext}\shell\{verb}"
        if _delete_key_tree(CLASSES_ROOT, shell_key_path):
            removed.append(f"{from_ext} -> {to_ext}")
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
