"""Proteus CLI entry point.

`install-context-menu`/`uninstall-context-menu` land in Phase 6 once
windows/context_menu.py exists. `convert`, `list-formats`, and `doctor`
are real as of Phase 3, backed by core/registry.py.
"""

from __future__ import annotations

from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from proteus.core.converter import ConversionOptions
from proteus.core.errors import ProteusError
from proteus.core.registry import CONVERTER_REGISTRY, get_converter

app = typer.Typer(
    name="proteus",
    help="Local, privacy-first document-format converter.",
    no_args_is_help=True,
)

console = Console()
error_console = Console(stderr=True)


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
) -> None:
    """Convert INPUT_FILE to the format given by --to."""
    from_ext = input_file.suffix.lstrip(".").lower()
    to_ext = to.lstrip(".").lower()
    output_path = output if output is not None else input_file.with_suffix(f".{to_ext}")

    try:
        converter = get_converter(from_ext, to_ext)
        result = converter.convert(input_file, output_path, ConversionOptions())
    except ProteusError as e:
        error_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

    console.print(f"[bold green]Converted[/bold green] -> {result.output_path}")


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
