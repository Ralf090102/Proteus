"""Proteus CLI entry point.

Real commands (`convert`, `list-formats`, `doctor`, `install-context-menu`)
are wired up in Phase 3+ once the converter registry has real backends
behind it — see the roadmap. `version` is the one command registered now,
just so the Typer app is valid and `uv run proteus` / the packaged entry
point both resolve (a Typer app with zero commands can't build a CLI at
all, even for `--help`).
"""

from importlib.metadata import version as _pkg_version

import typer

app = typer.Typer(
    name="proteus",
    help="Local, privacy-first document-format converter.",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """Local, privacy-first document-format converter."""


@app.command()
def version() -> None:
    """Print the installed Proteus version."""
    typer.echo(_pkg_version("proteus"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
