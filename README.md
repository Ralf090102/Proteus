# Proteus

Local, privacy-first document-format converter — a CLI (plus an optional Windows right-click
context-menu layer) to replace ad-hoc "convert my docx to pdf" web tools. Nothing leaves your
machine.

## Status

v1 is done. All conversion pairs work end to end (`docx→pdf`, `docx↔md`, `md→pdf`, `pdf→docx`,
`pdf→txt`), the Windows right-click context-menu layer is built and installable (with a
"Replace Original" variant per pair, and no console/Explorer-window flash — see below), and
`doctor` reports exactly what's missing and where to get it.

## Why

Generic online converter sites mean uploading your documents to a third party just to change
their format. Proteus does the same conversions locally, using tools you already have (or can
install once): Pandoc and LibreOffice.

## v1 scope

| Pair | Backend |
|---|---|
| `docx → pdf` | LibreOffice headless |
| `docx → md` | Pandoc |
| `md → docx` | Pandoc |
| `md → pdf` | Pandoc → docx, then LibreOffice → pdf (chained) |
| `pdf → docx` | `pdf2docx` |
| `pdf → txt` | PyMuPDF |

## Adding a new format pair

Every pair is one entry in a hand-maintained registry (`src/proteus/core/registry.py`) — a
`dict[tuple[from_ext, to_ext], type[Converter]]` — so adding one that reuses an existing backend
is a two-line change, not a redesign. `pptx → pdf`, for example, needs nothing new: LibreOffice
headless already handles `.pptx` natively, so it's the same `LibreOfficeConverter` the
`docx → pdf` pair already uses:

```python
# src/proteus/core/registry.py
CONVERTER_REGISTRY: dict[tuple[str, str], type[Converter]] = {
    ...
    ("pptx", "pdf"): LibreOfficeConverter,  # new line
}
```

That's it — `convert`, `list-formats`, and `doctor` all pick it up automatically, since every one
of them just iterates the registry.

A pair that needs a genuinely new backend (a different external tool, or a different in-process
library) means implementing the `Converter` ABC once
(`src/proteus/core/converter.py`) — see `converters/libreoffice.py` or `converters/pandoc.py` as
a template for a subprocess-backed converter, or `converters/pdf_extract.py` for a
library-backed one — then registering it the same way. Add a matching unit test against a
mocked/faked backend per `CLAUDE.md`'s testing convention.

## Stack

Python 3.12+, [`uv`](https://docs.astral.sh/uv/) for dependency management, `src/` layout,
setuptools build backend, [Typer](https://typer.tiangolo.com/) + [rich](https://rich.readthedocs.io/)
for the CLI, pydantic for typed models. Windows integration via the stdlib `winreg` module (no
extra dependency, no COM/DLL registration).

## Installing

For everyday use — not just development — install Proteus as a standalone CLI tool rather than
running everything through `uv run`:

```powershell
uv tool install .
```

This builds **two** executables into `~/.local/bin` (which `uv tool install` adds to `PATH`
itself): `proteus`, the console CLI for terminal use, and `proteus-gui`, a windowed twin used
only by the right-click context menu below — so a conversion triggered from Explorer doesn't
flash a console window. After installing, run `proteus doctor` to confirm LibreOffice/Pandoc
resolve correctly (it prints an install link for anything missing).

After pulling new code, reinstall with `uv tool install . --reinstall` — a plain
`uv tool install .` on top of an existing install is a no-op.

## Windows right-click context menu

```powershell
proteus install-context-menu     # registers the menu (HKCU only — no admin rights)
proteus uninstall-context-menu   # removes everything it added, cleanly
```

Requires `uv tool install .` to have been run first (the registered command needs a stable exe
path to point at). Adds a "Proteus" submenu to every registered source extension's right-click
menu in Explorer, with **two** verbs per conversion pair — e.g. for a `.docx` file:

- **Convert to PDF** — converts, leaves the original `.docx` in place.
- **Convert to PDF (Replace Original)** — converts, then deletes the original `.docx` once the
  PDF is confirmed written (a failed delete, e.g. a file locked open elsewhere, is a warning, not
  a failed conversion).

Both run silently on success — no window of any kind opens. A failed conversion shows a native
error dialog instead (there's no console attached to a right-click launch to print to).

## Development

```powershell
uv sync              # install deps into .venv
uv run proteus        # run the CLI
uv run pytest         # unit tests (integration tests need real Pandoc/LibreOffice on PATH)
```

## License

[MIT](LICENSE)
