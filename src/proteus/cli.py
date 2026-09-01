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
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from proteus.core.converter import ConversionOptions
from proteus.core.errors import ProteusError
from proteus.core.registry import CONVERTER_REGISTRY, get_converter
from proteus.windows import context_menu

app = typer.Typer(
    name="proteus",
    help="Local, privacy-first document-format converter.",
    no_args_is_help=True,
)

console = Console()
error_console = Console(stderr=True)

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
    for (from_ext, to_ext), converter_class in sorted(CONVERTER_REGISTRY.items()):
        available = converter_class().is_available()
        status = "[green]yes[/green]" if available else "[red]no[/red]"
        table.add_row(f"{from_ext} -> {to_ext}", converter_class.__name__, status)
    console.print(table)


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
