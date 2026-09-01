# Proteus

Local, privacy-first document-format converter — a CLI (plus an optional Windows right-click
context-menu layer) to replace ad-hoc "convert my docx to pdf" web tools. Nothing leaves your
machine.

## Status

All v1 conversion pairs work end to end (`docx→pdf`, `docx↔md`, `md→pdf`, `pdf→docx`,
`pdf→txt`), and the Windows right-click context-menu layer is built and installable. Remaining:
Phase 7 polish (richer `doctor` output, install-links for missing tools, packaging notes).

## Why

Generic online converter sites mean uploading your documents to a third party just to change
their format. Proteus does the same conversions locally, using tools you already have (or can
install once): Pandoc and LibreOffice.

## Planned v1 scope

| Pair | Backend |
|---|---|
| `docx → pdf` | LibreOffice headless |
| `docx → md` | Pandoc |
| `md → docx` | Pandoc |
| `md → pdf` | Pandoc → docx, then LibreOffice → pdf (chained) |
| `pdf → docx` | `pdf2docx` |
| `pdf → txt` | PyMuPDF |

Every pair is one entry in a hand-maintained registry (`src/proteus/core/registry.py`), so
adding a new pair later (e.g. `pptx → pdf`) is a two-line addition, not a redesign.

## Stack

Python 3.12+, [`uv`](https://docs.astral.sh/uv/) for dependency management, `src/` layout,
setuptools build backend, [Typer](https://typer.tiangolo.com/) + [rich](https://rich.readthedocs.io/)
for the CLI, pydantic for typed models. Windows integration via the stdlib `winreg` module (no
extra dependency, no COM/DLL registration).

## Development

```powershell
uv sync              # install deps into .venv
uv run proteus        # run the CLI
uv run pytest         # unit tests (integration tests need real Pandoc/LibreOffice on PATH)
```

## License

[MIT](LICENSE)
