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
    DEFAULT_PDF_DPI,
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


def test_convert_does_not_destroy_pre_existing_output_on_failure(tmp_path):
    # Regression: Image.save() opens its target in "w+b" mode, truncating
    # a pre-existing file to 0 bytes *before* encoding a single byte, and
    # only cleans up on failure if the file didn't already exist. A
    # pre-existing output_path must survive a failed conversion untouched.
    bad_file = tmp_path / "not-an-image.png"
    bad_file.write_bytes(b"this is not an image")

    output_path = tmp_path / "out.jpg"
    output_path.write_text("important pre-existing content")

    with pytest.raises(ConversionFailedError):
        PngToJpgConverter().convert(bad_file, output_path, ConversionOptions())

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_cmyk_source_converts_to_jpeg_without_needing_to_flatten(tmp_path):
    # Regression for the broadened _JPEG_SAFE_MODES set: CMYK is directly
    # JPEG-savable per Pillow's own JpegImagePlugin.RAWMODE — must not
    # raise, and shouldn't need the RGB-flatten path (unlike RGBA/LA/P).
    cmyk_source = tmp_path / "cmyk.tif"
    Image.new("CMYK", (10, 8), (0, 0, 0, 0)).save(cmyk_source, format="TIFF")

    output_path = tmp_path / "out.jpg"
    result = PngToJpgConverter().convert(cmyk_source, output_path, ConversionOptions())

    assert result.output_path == output_path
    with Image.open(output_path) as img:
        assert img.format == "JPEG"


def test_tool_checks_reports_resolved_path_when_pillow_available():
    checks = PngToJpgConverter().tool_checks()
    assert len(checks) == 1
    bin_name, status, kind = checks[0]
    assert bin_name == "pillow"
    assert kind == "extra"
    assert status.available is True
    assert status.path is not None


# --- png/jpg/webp -> pdf ---
#
# Unlike the JPEG target, PDF needed no mode-flattening: confirmed
# directly against every relevant Pillow mode (RGBA, RGB, L, P, CMYK,
# 1-bit) before implementing, so there's no equivalent to the JPEG-target
# alpha-handling tests above — the regression coverage here is instead
# "converting a real-alpha source doesn't raise" plus the DPI/page-size
# behavior, which is genuinely new logic (see converters/image.py).


def test_png_to_pdf_converts(tmp_path):
    output_path = tmp_path / "out.pdf"
    result = PngToPdfConverter().convert(SAMPLE_PNG, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.read_bytes()[:5] == b"%PDF-"
    assert output_path.stat().st_size > 0


def test_jpg_to_pdf_converts(tmp_path):
    output_path = tmp_path / "out.pdf"
    result = JpgToPdfConverter().convert(SAMPLE_JPG, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.read_bytes()[:5] == b"%PDF-"
    assert output_path.stat().st_size > 0


def test_webp_to_pdf_converts(tmp_path):
    output_path = tmp_path / "out.pdf"
    result = WebpToPdfConverter().convert(SAMPLE_WEBP, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.read_bytes()[:5] == b"%PDF-"
    assert output_path.stat().st_size > 0


def test_png_to_pdf_preserves_alpha_source_without_flattening(tmp_path):
    # Regression for the empirical finding that PDF (unlike JPEG) needs no
    # alpha handling — sample.png/sample.webp both carry real alpha
    # transparency; the JPEG target would need to flatten these first
    # (see test_png_to_jpg_converts_and_flattens_alpha above), the PDF
    # target must not need to and must not raise.
    with Image.open(SAMPLE_PNG) as img:
        assert img.mode == "RGBA"

    output_path = tmp_path / "out.pdf"
    PngToPdfConverter().convert(SAMPLE_PNG, output_path, ConversionOptions())

    assert output_path.read_bytes()[:5] == b"%PDF-"


def test_pdf_target_uses_default_dpi_when_source_has_no_dpi_metadata(tmp_path):
    import pymupdf

    with Image.open(SAMPLE_PNG) as img:
        assert img.info.get("dpi") is None  # confirmed true for every fixture
        width_px, height_px = img.size

    output_path = tmp_path / "out.pdf"
    PngToPdfConverter().convert(SAMPLE_PNG, output_path, ConversionOptions())

    with pymupdf.open(output_path) as doc:
        page_rect = doc[0].rect
    expected_width_pt = width_px / DEFAULT_PDF_DPI * 72
    expected_height_pt = height_px / DEFAULT_PDF_DPI * 72
    assert page_rect.width == pytest.approx(expected_width_pt, abs=0.5)
    assert page_rect.height == pytest.approx(expected_height_pt, abs=0.5)


def test_pdf_target_honors_source_dpi_metadata_when_present(tmp_path):
    import pymupdf

    source_dpi = 200.0
    source_path = tmp_path / "with_dpi.png"
    with Image.open(SAMPLE_PNG) as img:
        width_px, height_px = img.size
        img.save(source_path, dpi=(source_dpi, source_dpi))

    output_path = tmp_path / "out.pdf"
    PngToPdfConverter().convert(source_path, output_path, ConversionOptions())

    with pymupdf.open(output_path) as doc:
        page_rect = doc[0].rect
    expected_width_pt = width_px / source_dpi * 72
    expected_height_pt = height_px / source_dpi * 72
    assert page_rect.width == pytest.approx(expected_width_pt, abs=0.5)
    assert page_rect.height == pytest.approx(expected_height_pt, abs=0.5)
    # Sanity: this must differ from what the no-metadata default would
    # produce, or the test wouldn't actually be distinguishing the two
    # code paths.
    assert page_rect.width != pytest.approx(width_px / DEFAULT_PDF_DPI * 72, abs=0.5)
