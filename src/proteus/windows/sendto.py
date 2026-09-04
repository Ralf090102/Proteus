"""Windows Send To integration — install/uninstall .lnk shortcuts in
shell:sendto for v3's "combine 2+ same-type files into one" feature.

Different Windows mechanism (and different reason) from
windows/context_menu.py's SystemFileAssociations verbs: a plain
per-extension shell verb fires once *per selected file*, never once with
the whole selection, and conditional "only show for 2+ files" visibility
is COM-only — both confirmed against Microsoft's own documentation during
v3's design (see Eru's Proteus-Roadmap.md, "v3 roadmap" section). Send To
is the mechanism that actually delivers a whole multi-file selection to
one process launch — confirmed directly with a real throwaway shortcut
during the same design pass (one PID, all selected paths in one argv).
So every shortcut here is always visible, for any selection, any count,
any type; validity (2+ files, all one extension, a Merger registered for
it) is checked at runtime instead, by cli.py's hidden `merge` command.

Every shortcut invokes that same `merge` command with no extension-
specific flag — MERGE_REGISTRY (core/registry.py) is keyed by extension
with no ambiguity, so whichever files were actually selected are enough
on their own to pick the right Merger. Shortcuts differ only in filename
(what Explorer shows in the Send To menu) and whether they carry
--replace-source.

.lnk creation/removal goes through PowerShell's WScript.Shell COM object,
shelled out via subprocess — confirmed working with no pywin32 dependency
needed (same "shell out to an OS-native tool" preference LibreOffice/
Pandoc already follow, see core/subprocess_utils.py). Much simpler than
context_menu.py's install/uninstall: no registry tree to walk, just named
files in one known folder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from proteus.core.dependencies import resolve_proteus_gui_exe_path

SENDTO_DIR = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "SendTo"

# Every merge target gets a plain shortcut plus a "(Replace Originals)"
# variant, mirroring windows/context_menu.py's per-pair replace verb.
# Labels are display-only — the extension of whatever files Explorer
# actually hands to `merge` is what picks the real Merger (MERGE_REGISTRY),
# not which shortcut was clicked.
TARGET_LABELS = ("Merge PDF", "Merge Markdown", "Merge Text", "Images to PDF")
REPLACE_SUFFIX = " (Replace Originals)"


def _shortcut_names() -> list[str]:
    names = []
    for label in TARGET_LABELS:
        names.append(label)
        names.append(f"{label}{REPLACE_SUFFIX}")
    return names


def _ps_escape(value: str) -> str:
    # Single-quoted PowerShell strings need only '' to escape a literal
    # single quote — nothing else is special inside them (unlike a
    # double-quoted string, which interpolates $variables).
    return value.replace("'", "''")


def _run_powershell(script: str) -> None:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError(
            f"PowerShell shortcut command failed: {result.stderr.strip() or result.stdout.strip()}"
        )


def _create_shortcut(lnk_path: Path, exe_path: Path, arguments: str) -> None:
    lnk_literal = _ps_escape(str(lnk_path))
    exe_literal = _ps_escape(str(exe_path))
    args_literal = _ps_escape(arguments)
    script = (
        f"$sc = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_literal}'); "
        f"$sc.TargetPath = '{exe_literal}'; "
        f"$sc.Arguments = '{args_literal}'; "
        "$sc.Save()"
    )
    _run_powershell(script)


def install() -> list[str]:
    """Install one Send To shortcut per merge target, plus a "(Replace
    Originals)" variant per target — 8 total. Returns the labels
    installed."""
    exe_path = resolve_proteus_gui_exe_path()
    SENDTO_DIR.mkdir(parents=True, exist_ok=True)

    installed = []
    for label in TARGET_LABELS:
        _create_shortcut(SENDTO_DIR / f"{label}.lnk", exe_path, "merge --from-context-menu")
        installed.append(label)

        replace_label = f"{label}{REPLACE_SUFFIX}"
        _create_shortcut(
            SENDTO_DIR / f"{replace_label}.lnk",
            exe_path,
            "merge --from-context-menu --replace-source",
        )
        installed.append(replace_label)
    return installed


def uninstall() -> list[str]:
    """Remove every proteus-installed Send To shortcut, if present.

    Safe to call even if nothing (or only some) were installed — a
    missing .lnk is skipped, not an error, matching
    context_menu.uninstall()'s existing contract. Returns the labels
    actually removed: only those whose .lnk file genuinely existed among
    TARGET_LABELS' *current* names get unlinked and reported.

    Unlike context_menu.uninstall() — which enumerates the live registry
    subkeys actually present, so it also catches entries from a pair
    that's since been removed from CONVERTER_REGISTRY — this checks a
    fixed candidate list derived from today's TARGET_LABELS rather than
    scanning SENDTO_DIR itself. A shortcut installed under a label that
    is later renamed or removed from TARGET_LABELS won't be found here
    and will be left behind as an orphaned .lnk file.
    """
    removed = []
    for name in _shortcut_names():
        lnk_path = SENDTO_DIR / f"{name}.lnk"
        if lnk_path.exists():
            lnk_path.unlink()
            removed.append(name)
    return removed
