"""Pillow-backed image-format converter: png<->jpg, webp<->jpg/png.

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
_PILLOW_FORMAT = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}

# Every Pillow image mode the JPEG plugin can save directly (Pillow's own
# JpegImagePlugin.RAWMODE) — anything else, not just the alpha-bearing
# modes (RGBA/LA/P), must be flattened to RGB first or Image.save() raises
# "cannot write mode X as JPEG" (confirmed against Pillow's source: I, F,
# and LAB are rejected too, not just the alpha/palette cases).
_JPEG_SAFE_MODES = {"1", "L", "RGB", "RGBX", "CMYK", "YCbCr"}


class PillowConverter(Converter):
    """Generic Pillow-backed image converter. Subclasses just set
    from_ext/to_ext — Image.open()/save() already dispatch on format, so
    no per-pair logic is needed beyond the JPEG-alpha handling below."""

    def is_available(self) -> bool:
        try:
            import PIL  # noqa: F401
        except ImportError:
            return False
        return True

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        try:
            import PIL

            status = AvailabilityStatus(True, Path(PIL.__file__).parent, "package")
        except ImportError:
            status = AvailabilityStatus(False, None, "not-found")
        return (ToolCheck(PILLOW_EXTRA_NAME, status, kind="extra"),)

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        try:
            from PIL import Image
        except ImportError as e:
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
                with Image.open(input_path) as img:
                    if target_format == "JPEG" and img.mode not in _JPEG_SAFE_MODES:
                        img = img.convert("RGB")
                    img.save(tmp_output, format=target_format)
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
