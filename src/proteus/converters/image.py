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

# Modes with no valid JPEG encoding (JPEG has no alpha channel) — flatten
# to RGB first rather than let Pillow raise "cannot write mode X as JPEG".
_NO_ALPHA_IN_JPEG_MODES = {"RGBA", "LA", "P"}


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

        try:
            target_format = _PILLOW_FORMAT[self.to_ext]
            with Image.open(input_path) as img:
                if target_format == "JPEG" and img.mode in _NO_ALPHA_IN_JPEG_MODES:
                    img = img.convert("RGB")
                img.save(output_path, format=target_format)
        except Exception as e:
            raise ConversionFailedError(f"Pillow failed to convert {input_path}: {e}") from e

        ensure_output_created(output_path, "Pillow")
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
