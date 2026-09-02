"""Real-conversion tests for the Pillow-backed image converters.

Pillow is an optional install (the `images` extra), not a hard
dependency like pdf2docx/PyMuPDF — importorskip at module level means
this whole file skips cleanly in an environment where the extra isn't
installed, rather than assuming it's always present. Availability/
missing-Pillow tests (which must always run) live in the separate
test_image_converter.py instead."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from proteus.converters.image import (  # noqa: E402
    JpgToPngConverter,
    JpgToWebpConverter,
    PngToJpgConverter,
    PngToWebpConverter,
    WebpToJpgConverter,
    WebpToPngConverter,
)
from proteus.core.converter import ConversionOptions  # noqa: E402
from proteus.core.errors import ConversionFailedError  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_PNG = FIXTURES / "sample.png"  # has real alpha transparency
SAMPLE_JPG = FIXTURES / "sample.jpg"
SAMPLE_WEBP = FIXTURES / "sample.webp"  # also has alpha


def test_png_to_jpg_converts_and_flattens_alpha(tmp_path):
    output_path = tmp_path / "out.jpg"
    result = PngToJpgConverter().convert(SAMPLE_PNG, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.exists()
    with Image.open(output_path) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"  # alpha successfully flattened, not left as RGBA


def test_jpg_to_png(tmp_path):
    output_path = tmp_path / "out.png"
    result = JpgToPngConverter().convert(SAMPLE_JPG, output_path, ConversionOptions())

    assert result.output_path == output_path
    with Image.open(output_path) as img:
        assert img.format == "PNG"


def test_webp_to_jpg_flattens_alpha(tmp_path):
    output_path = tmp_path / "out.jpg"
    WebpToJpgConverter().convert(SAMPLE_WEBP, output_path, ConversionOptions())

    with Image.open(output_path) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"


def test_webp_to_png(tmp_path):
    output_path = tmp_path / "out.png"
    WebpToPngConverter().convert(SAMPLE_WEBP, output_path, ConversionOptions())

    with Image.open(output_path) as img:
        assert img.format == "PNG"


def test_jpg_to_webp(tmp_path):
    output_path = tmp_path / "out.webp"
    JpgToWebpConverter().convert(SAMPLE_JPG, output_path, ConversionOptions())

    with Image.open(output_path) as img:
        assert img.format == "WEBP"


def test_png_to_webp_preserves_alpha(tmp_path):
    # Unlike the JPEG target, WebP supports alpha — the source's
    # transparency must survive, not get silently flattened the way the
    # to-JPEG path deliberately does.
    output_path = tmp_path / "out.webp"
    PngToWebpConverter().convert(SAMPLE_PNG, output_path, ConversionOptions())

    with Image.open(output_path) as img:
        assert img.format == "WEBP"
        assert img.mode in ("RGBA", "P")


def test_convert_raises_conversion_failed_for_invalid_image(tmp_path):
    bad_file = tmp_path / "not-an-image.png"
    bad_file.write_bytes(b"this is not an image")

    with pytest.raises(ConversionFailedError):
        PngToJpgConverter().convert(bad_file, tmp_path / "out.jpg", ConversionOptions())


def test_tool_checks_reports_resolved_path_when_pillow_available():
    checks = PngToJpgConverter().tool_checks()
    assert len(checks) == 1
    bin_name, status, kind = checks[0]
    assert bin_name == "pillow"
    assert kind == "extra"
    assert status.available is True
    assert status.path is not None
