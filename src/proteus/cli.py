"""Proteus CLI entry point.

`convert`, `list-formats`, `doctor` are real as of Phase 3; `convert`'s
`--from-context-menu` handling and `install-context-menu`/
`uninstall-context-menu` are real as of Phase 6, backed by
windows/context_menu.py. A context-menu-launched conversion is silent on
success (no console, no Explorer window) and only surfaces a native message
box on failure or on a non-fatal `--replace-source` warning; `--replace-source`
deletes the original file once conversion succeeds.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from proteus.converters.image import PILLOW_EXTRA_NAME, PILLOW_INSTALL_HINT
from proteus.converters.pdf_extract import PYMUPDF4LLM_EXTRA_NAME, PYMUPDF4LLM_INSTALL_HINT
from proteus.core.converter import ConversionOptions, ToolCheck
from proteus.core.dependencies import INSTALL_LINKS, WINGET_PACKAGE_IDS
from proteus.core.errors import ProteusError
from proteus.core.registry import CONVERTER_REGISTRY, get_converter, get_merger
from proteus.windows import context_menu, sendto

app = typer.Typer(
    name="proteus",
    help="Local, privacy-first document-format converter.",
    no_args_is_help=True,
)

console = Console()
error_console = Console(stderr=True)

# Every ToolCheck kind="extra" bin_name mapped to its `uv tool install`
# hint — one entry per optional Python extra, sourced from that extra's
# own converter module so the hint text has exactly one home. Doctor's
# missing-tool list and install-deps' extras summary both key off this
# instead of hardcoding a single extra's hint, which only ever worked
# by accident while Pillow was the only optional extra that existed.
EXTRA_INSTALL_HINTS: dict[str, str] = {
    PILLOW_EXTRA_NAME: PILLOW_INSTALL_HINT,
    PYMUPDF4LLM_EXTRA_NAME: PYMUPDF4LLM_INSTALL_HINT,
}

_MB_ICONERROR = 0x10
_MB_ICONWARNING = 0x30


@app.callback()
def _callback() -> None:
    """Local, privacy-first document-format converter."""


@app.command()
def version() -> None:
    """Print the installed Proteus version."""
    typer.echo(_pkg_version("proteus"))


@app.command()
def convert(
    input_file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="File to convert."
    ),
    to: str = typer.Option(..., "--to", help="Target format, e.g. pdf"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output path (default: input file, new extension)."
    ),
    replace_source: bool = typer.Option(
        False,
        "--replace-source",
        help="Delete the original file after a successful conversion.",
    ),
    from_context_menu: bool = typer.Option(
        False,
        "--from-context-menu",
        hidden=True,
        help="Internal: invoked via the right-click context menu (no console attached).",
    ),
) -> None:
    """Convert INPUT_FILE to the format given by --to."""
    from_ext = input_file.suffix.lstrip(".").lower()
    to_ext = to.lstrip(".").lower()

    if not to_ext or not to_ext.isalnum():
        _report_error(
            f"Invalid target format {to!r} — expected a bare extension like 'pdf'.",
            from_context_menu,
        )
        raise typer.Exit(1)

    output_path = output if output is not None else input_file.with_suffix(f".{to_ext}")

    try:
        converter = get_converter(from_ext, to_ext)
        result = converter.convert(input_file, output_path, ConversionOptions())
    except ProteusError as e:
        _report_error(str(e), from_context_menu)
        raise typer.Exit(1) from None

    if replace_source and result.output_path.resolve() != input_file.resolve():
        try:
            input_file.unlink()
        except OSError as e:
            # The conversion itself succeeded — a locked/in-use source file
            # not being deletable is a non-fatal warning, not a command
            # failure.
            _report_warning(
                f"Converted, but couldn't delete the original file: {e}", from_context_menu
            )

    if not from_context_menu:
        console.print(f"[bold green]Converted[/bold green] -> {escape(str(result.output_path))}")


@app.command(hidden=True)
def merge(
    files: list[Path] = typer.Argument(
        ..., exists=True, dir_okay=False, help="Files to merge (2 or more, same type)."
    ),
    replace_source: bool = typer.Option(
        False,
        "--replace-source",
        help="Delete the original files after a successful merge.",
    ),
    from_context_menu: bool = typer.Option(
        False,
        "--from-context-menu",
        hidden=True,
        help="Internal: invoked via a Send To shortcut (no console attached).",
    ),
) -> None:
    """Merge 2+ same-type FILES into one.

    Hidden and internal — not meant to be typed directly. Reachable only
    via the Send To shortcuts windows/sendto.py installs, which is the
    only mechanism that can deliver a whole multi-file selection to one
    command invocation (see windows/sendto.py's module docstring)."""
    if len(files) < 2:
        _report_error("Select at least 2 files to merge.", from_context_menu)
        raise typer.Exit(1)

    extensions = {f.suffix.lstrip(".").lower() for f in files}
    if len(extensions) > 1:
        _report_error(
            f"All selected files must be the same type (got: {', '.join(sorted(extensions))}).",
            from_context_menu,
        )
        raise typer.Exit(1)

    try:
        merger = get_merger(extensions.pop())
    except ProteusError as e:
        _report_error(str(e), from_context_menu)
        raise typer.Exit(1) from None

    # Order: alphabetical by filename, decided here rather than trusted
    # from Explorer — confirmed during v3's design spike that Send To's
    # raw argument order is not alphabetical (selection/OS order instead).
    sorted_files = sorted(files, key=lambda f: f.name)
    output_path = _auto_merge_output_path(sorted_files[0].parent, merger.to_ext)

    try:
        result = merger.merge(sorted_files, output_path)
    except ProteusError as e:
        _report_error(str(e), from_context_menu)
        raise typer.Exit(1) from None

    if replace_source:
        delete_failures = []
        for f in sorted_files:
            try:
                f.unlink()
            except OSError as e:
                delete_failures.append(f"{f.name}: {e}")
        if delete_failures:
            # Same non-fatal-warning treatment as convert()'s
            # --replace-source path — the merge itself already succeeded.
            _report_warning(
                "Merged, but couldn't delete some original files: "
                + "; ".join(delete_failures),
                from_context_menu,
            )

    if not from_context_menu:
        console.print(f"[bold green]Merged[/bold green] -> {escape(str(result.output_path))}")


def _auto_merge_output_path(directory: Path, ext: str) -> Path:
    """merge has no CLI-equivalent naming convention to fall back on (it's
    only ever reachable via Send To, with no output-path flag at all) —
    the name has to be fully automatic. "merged.{ext}", collision-avoided
    with a "(1)", "(2)", ... suffix rather than overwriting."""
    candidate = directory / f"merged.{ext}"
    if not candidate.exists():
        return candidate
    n = 1
    while True:
        candidate = directory / f"merged ({n}).{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def _report_error(message: str, from_context_menu: bool) -> None:
    """Report a convert() failure — a right-click launch has no console
    attached at all, so writing to error_console isn't just invisible, it
    can itself raise. Show a native message box there instead."""
    if from_context_menu:
        _show_message_box("Proteus — Conversion Failed", message, icon=_MB_ICONERROR)
    else:
        error_console.print(f"[bold red]Error:[/bold red] {escape(message)}")


def _report_warning(message: str, from_context_menu: bool) -> None:
    """Report a non-fatal issue after an otherwise-successful conversion
    (e.g. --replace-source couldn't delete the original) — same
    console/message-box split as _report_error, but doesn't fail the
    command."""
    if from_context_menu:
        _show_message_box("Proteus — Warning", message, icon=_MB_ICONWARNING)
    else:
        console.print(f"[bold yellow]Warning:[/bold yellow] {escape(message)}")


def _show_message_box(title: str, message: str, *, icon: int = _MB_ICONERROR) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, title, icon)


@app.command(name="list-formats")
def list_formats() -> None:
    """List every registered conversion pair."""
    table = Table(title="Registered conversion pairs")
    table.add_column("From")
    table.add_column("To")
    for from_ext, to_ext in sorted(CONVERTER_REGISTRY.keys()):
        table.add_row(from_ext, to_ext)
    console.print(table)


@app.command()
def doctor() -> None:
    """Check whether each registered converter's backend is available."""
    table = Table(title="Proteus doctor")
    table.add_column("Pair")
    table.add_column("Converter")
    table.add_column("Available")
    table.add_column("Details")

    for (from_ext, to_ext), converter_class in sorted(CONVERTER_REGISTRY.items()):
        converter = converter_class()
        checks = converter.tool_checks()
        available = converter.is_available()
        status = "[green]yes[/green]" if available else "[red]no[/red]"
        table.add_row(
            f"{from_ext} -> {to_ext}",
            converter_class.__name__,
            status,
            _doctor_details(checks),
        )
    console.print(table)

    # Install links get printed separately below the table, not squeezed
    # into a table cell — a long URL truncates with a "…" inside a narrow
    # table column (confirmed: rich's default 80-col fallback width cuts
    # every LibreOffice/Pandoc download link short), which would defeat
    # the whole point of showing it.
    missing_tools = _collect_missing_tools()
    if missing_tools:
        console.print()
        console.print("[bold yellow]Install missing tools:[/bold yellow]")
        for bin_name, kind in missing_tools.items():
            console.print(escape(_missing_tool_line(bin_name, kind)))
        if any(
            kind == "tool" and bin_name in WINGET_PACKAGE_IDS
            for bin_name, kind in missing_tools.items()
        ):
            console.print()
            console.print(
                "Or run [bold]proteus install-deps[/bold] to install automatically via winget."
            )


def _missing_tool_line(bin_name: str, kind: str) -> str:
    """One line for a missing dependency — an optional Python extra
    (kind="extra", e.g. Pillow) has no download-page link, its fix is a
    `uv tool install` command; an external tool (kind="tool") uses
    INSTALL_LINKS same as always."""
    if kind == "extra":
        hint = EXTRA_INSTALL_HINTS.get(bin_name, "<no install hint registered>")
        return f"  {bin_name} — optional extra not installed, run: {hint}"
    return _manual_install_line(bin_name)


def _doctor_details(checks: tuple[ToolCheck, ...]) -> str:
    """Build doctor's Details cell for one converter: where each required
    tool was found, or a short "not found"/"optional extra not installed"
    flag — the full install link for anything missing goes in the
    separate list doctor() prints below the table instead (see there for
    why)."""
    if not checks:
        return "bundled Python library — no external tool needed"

    parts = []
    for bin_name, status, kind in checks:
        if status.available:
            parts.append(f"{bin_name}: {status.path}")
        elif kind == "extra":
            parts.append(f"{bin_name}: optional extra not installed")
        else:
            parts.append(f"{bin_name}: not found")
    return escape(" | ".join(parts))


def _collect_missing_tools() -> dict[str, str]:
    """Every distinct external-tool/optional-extra bin_name that's missing
    across all registered converters, in first-seen order, deduped (a
    dependency missing for multiple pairs — e.g. soffice for both
    docx->pdf and the md->pdf chain — is only counted once), mapped to
    its ToolCheck kind ("tool" | "extra"). Shared by doctor() and
    install_deps().

    Raises RuntimeError for any other kind value — doctor()/install_deps()
    both branch on exactly "tool"/"extra"; silently falling through to
    neither branch (which an unvalidated typo would do) makes install-deps
    exit 0 with no output at all, as if nothing were missing, while a real
    dependency is unresolved. Loud failure here beats a silent no-op.
    """
    missing: dict[str, str] = {}
    for converter_class in CONVERTER_REGISTRY.values():
        for bin_name, status, kind in converter_class().tool_checks():
            if kind not in ("tool", "extra"):
                raise RuntimeError(
                    f"{converter_class.__name__}.tool_checks() returned an unrecognized "
                    f"ToolCheck kind {kind!r} for {bin_name!r} — expected 'tool' or 'extra'"
                )
            if not status.available:
                missing.setdefault(bin_name, kind)
    return missing


@app.command(name="install-deps")
def install_deps() -> None:
    """Install missing external tools (LibreOffice, Pandoc) via winget.

    Optional Python-package extras (e.g. Pillow for image conversion) are
    a different install path entirely — `uv tool install .[images]`, not
    an external binary winget can install — so those are only reported
    here (see _print_extras_hint), never attempted.
    """
    missing_tools = _collect_missing_tools()
    if not missing_tools:
        console.print("[bold green]Everything needed is already installed.[/bold green]")
        return

    tools_missing = [b for b, kind in missing_tools.items() if kind == "tool"]
    extras_missing = [b for b, kind in missing_tools.items() if kind == "extra"]

    if not tools_missing:
        _print_extras_hint(extras_missing)
        return

    installable = {b: WINGET_PACKAGE_IDS[b] for b in tools_missing if b in WINGET_PACKAGE_IDS}
    not_installable = [b for b in tools_missing if b not in installable]

    if installable and shutil.which("winget") is None:
        error_console.print(
            "[bold red]Error:[/bold red] winget was not found on PATH. Install "
            "'App Installer' from the Microsoft Store, or install these manually:"
        )
        for bin_name in tools_missing:
            console.print(escape(_manual_install_line(bin_name)))
        _print_extras_hint(extras_missing)
        raise typer.Exit(1)

    succeeded: list[str] = []
    failed: list[str] = []
    for bin_name, package_id in installable.items():
        console.print(f"[bold]Installing {bin_name}[/bold] ({package_id}) via winget...")
        if _install_via_winget(package_id):
            console.print("[green]  done[/green]")
            succeeded.append(bin_name)
        else:
            console.print(f"[red]  winget install failed for {bin_name}[/red]")
            failed.append(bin_name)

    if not_installable:
        console.print()
        console.print("[bold yellow]No winget package for:[/bold yellow]")
        for bin_name in not_installable:
            console.print(escape(_manual_install_line(bin_name)))

    console.print()
    if failed or not_installable:
        console.print(
            f"[bold yellow]{len(succeeded)} installed, {len(failed)} failed, "
            f"{len(not_installable)} need manual install.[/bold yellow] "
            "Run [bold]proteus doctor[/bold] to confirm."
        )
        _print_extras_hint(extras_missing)
        # Exit non-zero whenever anything short of full success happened —
        # not just when *everything* failed. A caller scripting
        # `proteus install-deps && proteus doctor` must see partial
        # failure as failure, not success just because something else
        # also happened to succeed.
        raise typer.Exit(1)

    console.print(
        f"[bold green]Installed {len(succeeded)} tool(s).[/bold green] "
        "Run [bold]proteus doctor[/bold] to confirm."
    )
    _print_extras_hint(extras_missing)


def _print_extras_hint(extras_missing: list[str]) -> None:
    """Optional Python-package extras never go through winget — report
    them separately rather than folding into the tools summary/exit code
    above, since install-deps has nothing to automate for them."""
    if not extras_missing:
        return
    console.print()
    console.print("[bold yellow]Optional extras not installed:[/bold yellow]")
    for bin_name in extras_missing:
        hint = EXTRA_INSTALL_HINTS.get(bin_name, "<no install hint registered>")
        console.print(escape(f"  {bin_name} — run: {hint}"))


def _manual_install_line(bin_name: str) -> str:
    link = INSTALL_LINKS.get(bin_name)
    return f"  {bin_name} — {link}" if link else f"  {bin_name}"


def _install_via_winget(package_id: str) -> bool:
    """Run a silent winget install for one package.

    Deliberately not run through core/subprocess_utils.run_subprocess():
    that helper captures/suppresses output for a no-console context-menu
    launch, but install-deps is CLI-only (never invoked from the context
    menu) and its winget calls are foreground, user-triggered, and can be
    a large download (LibreOffice) — letting winget's own progress output
    stream straight to the console matters here.
    """
    result = subprocess.run(
        [
            "winget",
            "install",
            "--id",
            package_id,
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
    )
    return result.returncode == 0


@app.command(name="install-context-menu")
def install_context_menu() -> None:
    """Register a right-click 'Convert to ...' verb for every registered
    pair (HKCU only — no admin rights needed)."""
    try:
        installed = context_menu.install()
    except (RuntimeError, OSError) as e:
        _report_error(str(e), from_context_menu=False)
        raise typer.Exit(1) from None

    console.print(f"[bold green]Installed[/bold green] {len(installed)} context-menu verb(s):")
    for pair in installed:
        console.print(f"  {pair}")


@app.command(name="uninstall-context-menu")
def uninstall_context_menu() -> None:
    """Remove every proteus-installed right-click verb."""
    try:
        removed = context_menu.uninstall()
    except OSError as e:
        _report_error(str(e), from_context_menu=False)
        raise typer.Exit(1) from None

    if not removed:
        console.print("[yellow]No proteus context-menu entries were installed.[/yellow]")
        return

    console.print(f"[bold green]Removed[/bold green] {len(removed)} context-menu verb(s):")
    for pair in removed:
        console.print(f"  {pair}")


@app.command(name="install-sendto")
def install_sendto() -> None:
    """Register a Send To shortcut for each merge target (pdf/md/txt
    merge, images -> pdf), plus a "(Replace Originals)" variant per
    target — 8 shortcuts, in Explorer's Send To menu (no admin rights
    needed)."""
    try:
        installed = sendto.install()
    except (RuntimeError, OSError) as e:
        _report_error(str(e), from_context_menu=False)
        raise typer.Exit(1) from None

    console.print(f"[bold green]Installed[/bold green] {len(installed)} Send To shortcut(s):")
    for label in installed:
        console.print(f"  {label}")


@app.command(name="uninstall-sendto")
def uninstall_sendto() -> None:
    """Remove every proteus-installed Send To shortcut."""
    try:
        removed = sendto.uninstall()
    except OSError as e:
        _report_error(str(e), from_context_menu=False)
        raise typer.Exit(1) from None

    if not removed:
        console.print("[yellow]No proteus Send To shortcuts were installed.[/yellow]")
        return

    console.print(f"[bold green]Removed[/bold green] {len(removed)} Send To shortcut(s):")
    for label in removed:
        console.print(f"  {label}")


def main() -> None:
    """Entry point for both `proteus` (console-subsystem) and `proteus-gui`
    (windowed-subsystem, see [project.gui-scripts] in pyproject.toml — the
    context menu invokes this one, see windows/context_menu.py). A windowed
    process has no console to show a traceback in, so anything that escapes
    app()'s own ProteusError handling during a --from-context-menu run
    needs to become a message box instead of vanishing silently."""
    try:
        app()
    except SystemExit:
        raise
    except Exception as e:
        if "--from-context-menu" in sys.argv:
            _show_message_box("Proteus — Unexpected Error", str(e))
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
