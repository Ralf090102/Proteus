"""Pillow-backed image-format converter: png<->jpg, webp<->jpg/png,
png/jpg/webp -> pdf.

Unlike converters/pdf_extract.py's hard dependencies (pdf2docx, PyMuPDF),
Pillow is a genuinely optional install — the `images` extra in
pyproject.toml, not a base dependency, per the explicit v2 requirement
that image conversion can't become a hard dependency for core Proteus.
is_available() actually probes for it rather than always returning True.

PIL is imported lazily, inside is_available()/convert() rather than at
module level, same convention (and same reason) as pdf_extract.py: a
missing/broken Pillow install must not break every other pair's
doctor/convert, since core/registry.py imports every converter module
eagerly regardless of which pair is actually being run.
"""

from __future__ import annotations

import math
import os
import uuid
from pathlib import Path

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ToolCheck,
    ensure_output_created,
)
from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError

PILLOW_EXTRA_NAME = "pillow"
PILLOW_INSTALL_HINT = "uv tool install .[images]"

# Pillow's format names differ from bare extensions for jpg specifically
# (Image.save(format=...) expects "JPEG", not "JPG"); png/webp match.
_PILLOW_FORMAT = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "pdf": "PDF"}

# Pillow's PDF writer treats 1 source pixel as 1 PDF point (72dpi) unless
# given an explicit resolution= — confirmed directly: a 40x30px image
# produced a 40x30-*point* PDF page, which for a typical multi-thousand-
# pixel photo/scan means an absurdly oversized "page". Used only as a
# fallback below, when the source has no embedded DPI of its own.
DEFAULT_PDF_DPI = 96.0

# Every Pillow image mode the JPEG plugin can save directly (Pillow's own
# JpegImagePlugin.RAWMODE) — anything else, not just the alpha-bearing
# modes (RGBA/LA/P), must be flattened to RGB first or Image.save() raises
# "cannot write mode X as JPEG" (confirmed against Pillow's source: I, F,
# and LAB are rejected too, not just the alpha/palette cases).
_JPEG_SAFE_MODES = {"1", "L", "RGB", "RGBX", "CMYK", "YCbCr"}

# Every Pillow image mode the PDF plugin can save directly (Pillow's own
# PdfImagePlugin._save() mode dispatch, read directly from source) —
# anything else must be flattened to RGB first or Image.save() raises
# "cannot save mode X". Confirmed reachable from a real file: opening a
# 16-bit-depth grayscale PNG gives mode "I;16", which isn't in this set —
# that file converts fine to JPG/PNG/WEBP but previously failed outright
# for PDF, an asymmetric capability gap this flattening closes.
_PDF_SAFE_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}


def _resolve_pdf_dpi(img) -> tuple[float, float]:
    """The (x, y) DPI to write into a PDF target: the source's own
    embedded DPI when present and sane, else DEFAULT_PDF_DPI for both
    axes.

    Two real-world degenerate cases confirmed directly, not just "dpi key
    absent": (1) a 0 or negative value — reachable from real files (a PNG
    pHYs chunk with px=0/py=0, or a JPEG EXIF XResolution of 0/1; Pillow
    accepts both as valid `dpi` metadata) — reaching Pillow's PDF writer
    as `resolution=0` raises ZeroDivisionError (`width * 72.0 /
    x_resolution`), turning an otherwise-convertible file into a crash;
    (2) anisotropic (non-square) DPI silently collapsed to one axis by
    passing a single `resolution=` value instead of Pillow's two-axis
    `dpi=(x, y)` kwarg — confirmed a real 300x600 DPI (1in x 2in) source
    was distorted to a 1in x 1in page under `resolution=`, correct under
    `dpi=`. Both are guarded against here.
    """
    source_dpi = img.info.get("dpi")
    if not source_dpi:
        return (DEFAULT_PDF_DPI, DEFAULT_PDF_DPI)
    x_dpi, y_dpi = source_dpi[0], source_dpi[1]
    if not (math.isfinite(x_dpi) and x_dpi > 0):
        x_dpi = DEFAULT_PDF_DPI
    if not (math.isfinite(y_dpi) and y_dpi > 0):
        y_dpi = DEFAULT_PDF_DPI
    return (x_dpi, y_dpi)


class PillowConverter(Converter):
    """Generic Pillow-backed image converter. Subclasses just set
    from_ext/to_ext — Image.open()/save() already dispatch on format, so
    no per-pair logic is needed beyond the JPEG-alpha handling below."""

    def is_available(self) -> bool:
        try:
            import PIL  # noqa: F401
        except Exception:
            # Broader than ImportError deliberately: a genuinely broken
            # install (e.g. a corrupted native extension) can fail import
            # with something else entirely, and doctor()/list-formats()
            # iterate every registered converter's is_available() in one
            # pass — one broken optional install must not crash the
            # command for every other pair too. Same "no stable typed-
            # exception contract" reasoning already used for pdf2docx/
            # PyMuPDF in converters/pdf_extract.py.
            return False
        return True

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        try:
            import PIL

            status = AvailabilityStatus(True, Path(PIL.__file__).parent, "package")
        except Exception:
            status = AvailabilityStatus(False, None, "not-found")
        return (ToolCheck(PILLOW_EXTRA_NAME, status, kind="extra"),)

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        try:
            from PIL import Image
        except Exception as e:
            # Broader than ImportError here too (see is_available()'s
            # comment) — a broken, not just missing, install should still
            # surface as a clean ConverterUnavailableError with the
            # install hint, not a raw uncaught exception from deep
            # inside a native-extension import failure.
            raise ConverterUnavailableError(
                f"Pillow is not installed. Install the optional image-conversion "
                f"extra: {PILLOW_INSTALL_HINT}"
            ) from e

        # Write to a temp file in output_path's own directory (same drive,
        # so os.replace() below is atomic) rather than letting Pillow save
        # to output_path directly: Image.save() opens its target in
        # "w+b" mode, which truncates a pre-existing file to 0 bytes
        # *before* encoding a single byte, and only cleans up on failure
        # if the file didn't already exist beforehand — confirmed
        # empirically. So a save failure partway through (a source mode
        # not handled below, disk full, a locked destination) would
        # otherwise destroy whatever was already at output_path with no
        # recovery. Same reasoning as LibreOffice's shutil.move, simpler
        # here since the temp file lives right next to the destination.
        tmp_output = output_path.with_name(
            f".proteus-tmp-{uuid.uuid4().hex}{output_path.suffix}"
        )
        try:
            try:
                target_format = _PILLOW_FORMAT[self.to_ext]
                save_kwargs: dict[str, object] = {}
                with Image.open(input_path) as img:
                    if target_format == "PDF":
                        # Computed before any mode reassignment below —
                        # img.convert()'s effect on .info["dpi"] isn't
                        # something to depend on, so resolve DPI from the
                        # original decoded image. (WebP sources never
                        # carry dpi metadata regardless — Pillow's own
                        # WebP reader doesn't populate it even when the
                        # file has EXIF resolution tags, confirmed
                        # directly — so WebpToPdfConverter always lands on
                        # the DEFAULT_PDF_DPI fallback; not a bug here,
                        # just an inherent Pillow reader limitation.)
                        save_kwargs["dpi"] = _resolve_pdf_dpi(img)
                        if img.mode not in _PDF_SAFE_MODES:
                            img = img.convert("RGB")
                    if target_format == "JPEG" and img.mode not in _JPEG_SAFE_MODES:
                        img = img.convert("RGB")
                    # A multi-frame source (e.g. animated WebP) only ever
                    # contributes its first frame — Image.open() decodes
                    # frame 0 by default and this never passes
                    # save_all=True, so img.save() here only ever writes
                    # a single-page PDF/single-frame JPEG/PNG regardless
                    # of how many frames the source has. Deliberate for a
                    # 1-to-1 "convert this picture" tool, not a batch/
                    # animation converter — confirmed directly (a 3-frame
                    # animated WebP produces a 1-page PDF matching only
                    # the first frame, no error).
                    img.save(tmp_output, format=target_format, **save_kwargs)
            except Exception as e:
                raise ConversionFailedError(f"Pillow failed to convert {input_path}: {e}") from e

            ensure_output_created(tmp_output, "Pillow")

            try:
                os.replace(tmp_output, output_path)
            except OSError as e:
                raise ConversionFailedError(
                    f"Pillow produced {tmp_output} but couldn't move it to "
                    f"{output_path} (destination may be open elsewhere): {e}"
                ) from e
        except Exception:
            tmp_output.unlink(missing_ok=True)
            raise

        return ConversionResult(output_path=output_path)


class PngToJpgConverter(PillowConverter):
    from_ext = "png"
    to_ext = "jpg"


class JpgToPngConverter(PillowConverter):
    from_ext = "jpg"
    to_ext = "png"


class WebpToJpgConverter(PillowConverter):
    from_ext = "webp"
    to_ext = "jpg"


class WebpToPngConverter(PillowConverter):
    from_ext = "webp"
    to_ext = "png"


class JpgToWebpConverter(PillowConverter):
    from_ext = "jpg"
    to_ext = "webp"


class PngToWebpConverter(PillowConverter):
    from_ext = "png"
    to_ext = "webp"


class PngToPdfConverter(PillowConverter):
    from_ext = "png"
    to_ext = "pdf"


class JpgToPdfConverter(PillowConverter):
    from_ext = "jpg"
    to_ext = "pdf"


class WebpToPdfConverter(PillowConverter):
    from_ext = "webp"
    to_ext = "pdf"
