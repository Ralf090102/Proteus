# Proteus

Local, privacy-first document-format converter. CLI first (Typer + rich), plus a Windows
Explorer right-click context-menu layer. No file ever leaves the machine — all conversion goes
through local tools (Pandoc, LibreOffice) or in-process libraries.

## Status

All v1 conversion pairs work end to end (`docx→pdf`, `docx↔md`, `md→pdf`, `pdf→docx`,
`pdf→txt`), and the Windows right-click context-menu layer (`windows/context_menu.py`,
`install-context-menu`/`uninstall-context-menu`) is built and installable. v2 additions: bug
sweep, `install-deps` (winget-based), `png↔jpg`/`webp↔jpg/png` (optional `images` extra),
`pptx→pdf`/`ppt→pdf` (LibreOffice, reusing the same backend as `docx→pdf`), `pdf→md`
(`pymupdf4llm`, optional `markdown` extra — a feasibility spike that cleared its quality bar
against a 400+ page real-world document and a two-column academic paper, no dropped content,
correct multi-column reading order, dense multi-line tables converting to real markdown grid
syntax), and `png/jpg/webp→pdf` (same Pillow/`images` extra as the other image pairs — Pillow
writes PDF natively, no mode-flattening needed for any source mode, confirmed directly against
RGBA/L/P/CMYK/1-bit).

## Architecture

One registry, pluggable backends — no single library converts every format pair well, so each
pair is a small `Converter` implementation registered under a `(from_ext, to_ext)` key:

- `core/registry.py` — hand-maintained `dict[tuple[str, str], Converter]` + `get_converter()`.
  Adding a new pair is adding an entry here, not writing a new subsystem.
- `core/converter.py` — the `Converter` ABC plus `ConversionOptions` / `ConversionResult`
  (pydantic models).
- `core/errors.py` — `ProteusError` and its subclasses (`UnknownConversionError`,
  `ConverterUnavailableError`, `ConversionFailedError`).
- `core/dependencies.py` — `find_tool()`: env var override → `shutil.which()` → known Windows
  install paths → not found. Every subprocess-backed converter resolves its binary through
  this (not a bare `shutil.which()` call), so `is_available()` and the actual command it runs
  always agree — installers don't reliably add themselves to PATH (confirmed for real with
  both LibreOffice and Pandoc during development).
- `converters/` — one module per backend (`libreoffice.py`, `pandoc.py`, `pdf_extract.py`,
  `chains.py` for composite conversions like `md → pdf`).
- `windows/context_menu.py` — `winreg`-based install/uninstall of a nested "Proteus" cascading
  submenu per source extension, under
  `HKCU\Software\Classes\SystemFileAssociations\.{ext}\shell\proteus_menu\shell\proteus_convert_to_{ext}`
  (the `proteus_menu` parent sets `MUIVerb`/`SubCommands=""`, the documented static-cascading-menu
  mechanism), derived from the registry. No COM/DLL — HKCU-only, no admin rights needed. All keys
  `proteus_`-prefixed so uninstall removes exactly what install created.
- `cli.py` — the Typer app (`proteus convert`, `list-formats`, `doctor`,
  `install-context-menu` / `uninstall-context-menu`).

## Planned v1 conversion pairs

`docx→pdf` (LibreOffice headless), `docx→md` / `md→docx` (Pandoc), `md→pdf` (Pandoc then
LibreOffice, chained), `pdf→docx` (`pdf2docx`), `pdf→txt` (PyMuPDF).

## v2 additions

`png↔jpg` / `webp↔jpg/png` (Pillow, optional `images` extra), `pptx→pdf` / `ppt→pdf`
(LibreOffice headless — same `LibreOfficeConverter` backend as `docx→pdf`; two thin subclasses,
`PptxToPdfConverter`/`PptToPdfConverter`, exist only to give the "tool not found" error message
the right pair name), `pdf→md` (`pymupdf4llm`, optional `markdown` extra — a much heavier
transitive install than Pillow, an ONNX layout model + onnxruntime + networkx, hence optional
rather than joining `pdf2docx`/`pymupdf` as a hard dependency), and `png/jpg/webp→pdf` (same
`images` extra/`PillowConverter` as the other image pairs — `Image.save(format="PDF")` needs no
new dependency or mode-flattening; the one real addition is honoring the source's embedded DPI
metadata when present, falling back to a fixed 96 DPI otherwise, since Pillow's own PDF-writer
default of 1px=1pt/72dpi would make a typical multi-thousand-pixel photo produce an absurdly
oversized page).

## Explicitly deferred (not forgotten)

xlsx conversions, OCR / scanned-PDF text, batch/folder conversion, any GUI or web UI, packaging
beyond `uv tool install`, vendoring Pandoc/LibreOffice. Don't build these speculatively — the
registry design keeps them cheap to add when actually needed.

## Development

```powershell
uv sync              # install deps into .venv
uv run proteus        # run the CLI
uv run pytest         # unit tests only (fast, no external tools required)
uv run pytest -m integration   # also exercises real Pandoc/LibreOffice — needs both on PATH
```

## Conventions

- `src/` layout; package name is `proteus`, import root is `proteus`.
- External tools (LibreOffice, Pandoc) are invoked as subprocesses, never vendored.
- Every real converter that shells out to an external tool (LibreOffice, Pandoc) needs a
  matching `tests/unit` test against a fake/double (mocked `find_tool`/`run_subprocess`),
  plus an opt-in `tests/integration` test against the real tool once that phase is reached.
  Exception: a converter wrapping a Python library that's a hard dependency (`pdf2docx`,
  PyMuPDF) has no "might not be installed" uncertainty to mock around, so its `tests/unit`
  tests run the real library directly against a fixture — no fake/double, no separate
  `integration`-marked duplicate of the same real test.
- Test fixtures (`tests/fixtures/`) are small, committed sample files (a `.docx` with a
  heading/list/table, a `.md` with heading/code-fence/table, a short `.pdf`) — not generated
  at test time.
