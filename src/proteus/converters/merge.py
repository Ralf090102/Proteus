"""Merge backends for v3's "combine 2+ same-type files into one" feature:
pdf merge (pymupdf), md/txt merge (plain concatenation), images -> one
combined multi-page PDF (Pillow). Invoked only via the hidden `merge` CLI
command (cli.py), itself only reachable from windows/sendto.py's Send To
shortcuts — see core/merger.py for the shared Merger contract.

pymupdf is imported lazily inside PdfMerger.merge(), same convention (and
same reason — a stray deprecation-warning leak on every unrelated
invocation) as converters/pdf_extract.py.
"""

from __future__ import annotations

from pathlib import Path

from proteus.converters.image import _PDF_SAFE_MODES, PILLOW_INSTALL_HINT, _resolve_pdf_dpi
from proteus.core.converter import ConversionResult, atomic_write
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError
from proteus.core.merger import Merger

# Separator between concatenated md/txt files — a blank line either side of
# a horizontal rule, distinct enough from ordinary content to visibly mark
# a join point without assuming anything about either file's own structure
# (a bare blank line alone could be mistaken for the source's own spacing).
_TEXT_JOIN_SEPARATOR = "\n\n---\n\n"


class PdfMerger(Merger):
    from_ext = "pdf"
    to_ext = "pdf"

    def is_available(self) -> bool:
        return True

    def merge(self, input_paths: list[Path], output_path: Path) -> ConversionResult:
        def write(tmp_output: Path) -> None:
            try:
                import pymupdf

                with pymupdf.open() as merged:
                    for path in input_paths:
                        with pymupdf.open(str(path)) as src:
                            merged.insert_pdf(src)
                    merged.save(str(tmp_output))
            except Exception as e:
                raise ConversionFailedError(
                    f"pymupdf failed to merge into {output_path}: {e}"
                ) from e

        return atomic_write(output_path, "pymupdf", write)


class _TextConcatMerger(Merger):
    """Shared implementation for MarkdownMerger/TextMerger — both are
    plain read-join-write, differing only in from_ext/to_ext."""

    def is_available(self) -> bool:
        return True

    def merge(self, input_paths: list[Path], output_path: Path) -> ConversionResult:
        def write(tmp_output: Path) -> None:
            try:
                contents = [path.read_text(encoding="utf-8") for path in input_paths]
                tmp_output.write_text(_TEXT_JOIN_SEPARATOR.join(contents), encoding="utf-8")
            except Exception as e:
                raise ConversionFailedError(
                    f"text-merge failed to merge into {output_path}: {e}"
                ) from e

        return atomic_write(output_path, "text-merge", write)


class MarkdownMerger(_TextConcatMerger):
    from_ext = "md"
    to_ext = "md"


class TextMerger(_TextConcatMerger):
    from_ext = "txt"
    to_ext = "txt"


class ImagesToPdfMerger(Merger):
    """Base class for the three thin subclasses below (Png/Jpg/WebpImagesToPdfMerger)
    registered in MERGE_REGISTRY under png/jpg/webp respectively — same
    "override from_ext/to_ext only" pattern converters/libreoffice.py's
    PptxToPdfConverter/PptToPdfConverter already established, needed here
    for the same reason: from_ext feeds error messages, so a single
    unparametrized class would mislabel which extension actually failed.
    to_ext is always "pdf" regardless of which one was selected.

    Reuses converters/image.py's PDF mode-safety set and DPI-resolution
    logic directly rather than duplicating it — both modules are doing the
    same "write these pixels into a PDF page" operation, just for one
    image (PillowConverter) vs. N images as N pages (here)."""

    to_ext = "pdf"

    def is_available(self) -> bool:
        try:
            import PIL  # noqa: F401
        except Exception:
            # Broader than ImportError deliberately — same reasoning as
            # PillowConverter.is_available() in converters/image.py.
            return False
        return True

    def merge(self, input_paths: list[Path], output_path: Path) -> ConversionResult:
        try:
            from PIL import Image
        except Exception as e:
            raise ConverterUnavailableError(
                f"Pillow is not installed. Install the optional image-conversion "
                f"extra: {PILLOW_INSTALL_HINT}"
            ) from e

        def write(tmp_output: Path) -> None:
            # Opened one at a time inside the try (not a list comprehension
            # ahead of it) so that if Image.open() raises partway through
            # (e.g. a corrupt file after N good ones), the already-opened
            # images are still deterministically closed by the finally
            # below instead of relying on GC to eventually finalize them.
            opened: list[Image.Image] = []
            try:
                try:
                    for path in input_paths:
                        opened.append(Image.open(path))
                    # Confirmed directly against Pillow's PdfImagePlugin
                    # source: a multi-page save reads `dpi=` once, from the
                    # *first* image's encoderinfo, and applies it to every
                    # page's MediaBox uniformly — per-page DPI is silently
                    # ignored for pages 2+ regardless of what's passed here.
                    # So only the first image's own DPI is worth resolving;
                    # a source set with genuinely mixed native DPIs (a phone
                    # photo alongside a scanned document, say) will have every
                    # page after the first sized using the first page's DPI,
                    # not its own. Accepted limitation — no clean per-page
                    # workaround exists through Pillow's single save() call.
                    pages = []
                    for img in opened:
                        if img.mode not in _PDF_SAFE_MODES:
                            img = img.convert("RGB")
                        pages.append(img)
                    first_dpi = _resolve_pdf_dpi(opened[0])
                    first_img, rest_imgs = pages[0], pages[1:]
                    first_img.save(
                        tmp_output,
                        format="PDF",
                        save_all=True,
                        append_images=rest_imgs,
                        dpi=first_dpi,
                    )
                finally:
                    for img in opened:
                        img.close()
            except Exception as e:
                raise ConversionFailedError(
                    f"Pillow failed to merge into {output_path}: {e}"
                ) from e

        return atomic_write(output_path, "Pillow", write)


class PngImagesToPdfMerger(ImagesToPdfMerger):
    from_ext = "png"


class JpgImagesToPdfMerger(ImagesToPdfMerger):
    from_ext = "jpg"


class WebpImagesToPdfMerger(ImagesToPdfMerger):
    from_ext = "webp"
