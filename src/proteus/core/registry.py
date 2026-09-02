"""(from_ext, to_ext) -> Converter class lookup.

Hand-maintained dict literal, deliberately — no plugin/entry-point
scanning, same pattern as lyra-mcp's STAGE_REGISTRY (src/lyra/registry.py).
This module only knows about extension-pair tuples and the Converter
class each one maps to; it has zero knowledge of the CLI or any specific
backend.

Adding a later pair (e.g. pptx->pdf) is a one-line addition, not a
redesign.
"""

from __future__ import annotations

from collections.abc import Mapping

from proteus.converters.chains import MarkdownToPdfChainConverter
from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.converters.pandoc import DocxToMarkdownConverter, MarkdownToDocxConverter
from proteus.converters.pdf_extract import Pdf2DocxConverter, PyMuPdfTextExtractConverter
from proteus.core.converter import Converter
from proteus.core.errors import UnknownConversionError

CONVERTER_REGISTRY: dict[tuple[str, str], type[Converter]] = {
    ("docx", "pdf"): LibreOfficeConverter,
    ("docx", "md"): DocxToMarkdownConverter,
    ("md", "docx"): MarkdownToDocxConverter,
    ("md", "pdf"): MarkdownToPdfChainConverter,
    ("pdf", "docx"): Pdf2DocxConverter,
    ("pdf", "txt"): PyMuPdfTextExtractConverter,
}


def get_converter(
    from_ext: str,
    to_ext: str,
    registry: Mapping[tuple[str, str], type[Converter]] = CONVERTER_REGISTRY,
) -> Converter:
    """Look up a (from_ext, to_ext) pair and construct its Converter.

    Raises UnknownConversionError, listing every known pair, if the pair
    isn't registered — an agent or user hitting this should be able to
    self-correct from the error message alone.
    """
    from_ext = from_ext.lower()
    to_ext = to_ext.lower()
    try:
        converter_class = registry[(from_ext, to_ext)]
    except KeyError:
        pairs = sorted(registry.keys())
        known = ", ".join(f"{a}->{b}" for a, b in pairs) or "(none registered yet)"
        raise UnknownConversionError(
            f"No converter registered for {from_ext!r} -> {to_ext!r}. Known pairs: {known}"
        ) from None
    return converter_class()
