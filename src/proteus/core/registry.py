"""(from_ext, to_ext) -> Converter class lookup.

Hand-maintained dict literal, deliberately — no plugin/entry-point
scanning, same pattern as lyra-mcp's STAGE_REGISTRY (src/lyra/registry.py).
This module only knows about extension-pair tuples and the Converter
class each one maps to; it has zero knowledge of the CLI or any specific
backend.

Adding a later pair reusing an existing backend (pptx->pdf/ppt->pdf via
LibreOfficeConverter were exactly this) is a one-line addition, not a
redesign.
"""

from __future__ import annotations

from collections.abc import Mapping

from proteus.converters.chains import MarkdownToPdfChainConverter
from proteus.converters.image import (
    JpgToPdfConverter,
    JpgToPngConverter,
    JpgToWebpConverter,
    PngToJpgConverter,
    PngToPdfConverter,
    PngToWebpConverter,
    WebpToJpgConverter,
    WebpToPdfConverter,
    WebpToPngConverter,
)
from proteus.converters.libreoffice import (
    LibreOfficeConverter,
    PptToPdfConverter,
    PptxToPdfConverter,
)
from proteus.converters.merge import (
    JpgImagesToPdfMerger,
    MarkdownMerger,
    PdfMerger,
    PngImagesToPdfMerger,
    TextMerger,
    WebpImagesToPdfMerger,
)
from proteus.converters.pandoc import DocxToMarkdownConverter, MarkdownToDocxConverter
from proteus.converters.pdf_extract import (
    Pdf2DocxConverter,
    PdfToMarkdownConverter,
    PyMuPdfTextExtractConverter,
)
from proteus.core.converter import Converter
from proteus.core.errors import UnknownConversionError
from proteus.core.merger import Merger

CONVERTER_REGISTRY: dict[tuple[str, str], type[Converter]] = {
    ("docx", "pdf"): LibreOfficeConverter,
    ("pptx", "pdf"): PptxToPdfConverter,
    # No dedicated fixture/integration test for legacy .ppt: a real
    # binary .ppt fixture is ~640KB (vs. every other fixture's low tens
    # of KB, or less) for content identical to sample.pptx — manually
    # verified against real LibreOffice instead (converts cleanly, same
    # LibreOfficeConverter.convert() as pptx/docx, which is provably
    # format-agnostic — see converters/libreoffice.py). Regression
    # coverage is the registry-resolution unit test only.
    ("ppt", "pdf"): PptToPdfConverter,
    ("docx", "md"): DocxToMarkdownConverter,
    ("md", "docx"): MarkdownToDocxConverter,
    ("md", "pdf"): MarkdownToPdfChainConverter,
    ("pdf", "docx"): Pdf2DocxConverter,
    ("pdf", "txt"): PyMuPdfTextExtractConverter,
    ("pdf", "md"): PdfToMarkdownConverter,
    ("png", "jpg"): PngToJpgConverter,
    ("jpg", "png"): JpgToPngConverter,
    ("webp", "jpg"): WebpToJpgConverter,
    ("webp", "png"): WebpToPngConverter,
    ("jpg", "webp"): JpgToWebpConverter,
    ("png", "webp"): PngToWebpConverter,
    ("png", "pdf"): PngToPdfConverter,
    ("jpg", "pdf"): JpgToPdfConverter,
    ("webp", "pdf"): WebpToPdfConverter,
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


# extension -> Merger lookup for v3's "combine 2+ same-type files into one"
# feature (windows/sendto.py + cli.py's hidden `merge` command) — parallel
# to CONVERTER_REGISTRY above, but keyed by one shared extension instead of
# a (from_ext, to_ext) pair, since a merge's output format is implicit
# (Merger.to_ext) rather than something the caller chooses. No ambiguity
# results from this: png/jpg/webp all map to their own thin
# ImagesToPdfMerger subclass (see converters/merge.py) purely so error
# messages name the right extension, not because the merge behavior
# differs.
MERGE_REGISTRY: dict[str, type[Merger]] = {
    "pdf": PdfMerger,
    "md": MarkdownMerger,
    "txt": TextMerger,
    "png": PngImagesToPdfMerger,
    "jpg": JpgImagesToPdfMerger,
    "webp": WebpImagesToPdfMerger,
}


def get_merger(
    ext: str,
    registry: Mapping[str, type[Merger]] = MERGE_REGISTRY,
) -> Merger:
    """Look up ext and construct its Merger.

    Raises UnknownConversionError, listing every known merge extension, if
    ext isn't registered — same self-correcting-error-message contract as
    get_converter() above.
    """
    ext = ext.lower()
    try:
        merger_class = registry[ext]
    except KeyError:
        known = ", ".join(sorted(registry.keys())) or "(none registered yet)"
        raise UnknownConversionError(
            f"No merger registered for {ext!r}. Known merge extensions: {known}"
        ) from None
    return merger_class()
