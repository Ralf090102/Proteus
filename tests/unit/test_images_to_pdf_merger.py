"""Real-merge tests for ImagesToPdfMerger and its Png/Jpg/Webp subclasses.

Pillow is an optional install (the `images` extra) — importorskip at
module level means this whole file skips cleanly when the extra isn't
installed, same convention as test_image_converter_real.py."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from proteus.converters.merge import (  # noqa: E402
    JpgImagesToPdfMerger,
    PngImagesToPdfMerger,
    WebpImagesToPdfMerger,
)
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_PNG = FIXTURES / "sample.png"
SAMPLE_JPG = FIXTURES / "sample.jpg"
SAMPLE_WEBP = FIXTURES / "sample.webp"


def test_is_available_true_when_pillow_installed():
    assert PngImagesToPdfMerger().is_available() is True


def test_png_images_merge_into_two_page_pdf(tmp_path):
    output_path = tmp_path / "merged.pdf"
    result = PngImagesToPdfMerger().merge([SAMPLE_PNG, SAMPLE_PNG], output_path)

    assert result.output_path == output_path
    assert output_path.read_bytes()[:5] == b"%PDF-"

    import pymupdf

    with pymupdf.open(output_path) as doc:
        assert doc.page_count == 2


def test_jpg_images_merge_into_pdf(tmp_path):
    output_path = tmp_path / "merged.pdf"
    JpgImagesToPdfMerger().merge([SAMPLE_JPG, SAMPLE_JPG, SAMPLE_JPG], output_path)

    import pymupdf

    with pymupdf.open(output_path) as doc:
        assert doc.page_count == 3


def test_webp_images_with_alpha_merge_without_raising(tmp_path):
    # sample.webp carries real alpha transparency, same as the single-image
    # converter's tests — must flatten cleanly for a PDF target, same
    # _PDF_SAFE_MODES logic reused from converters/image.py.
    output_path = tmp_path / "merged.pdf"
    result = WebpImagesToPdfMerger().merge([SAMPLE_WEBP, SAMPLE_WEBP], output_path)

    assert output_path.read_bytes()[:5] == b"%PDF-"
    assert result.output_path == output_path


def test_merge_raises_conversion_failed_for_invalid_image(tmp_path):
    bad_file = tmp_path / "not-an-image.png"
    bad_file.write_bytes(b"this is not an image")

    with pytest.raises(ConversionFailedError):
        PngImagesToPdfMerger().merge([SAMPLE_PNG, bad_file], tmp_path / "out.pdf")


def test_merge_does_not_destroy_pre_existing_output_on_failure(tmp_path):
    bad_file = tmp_path / "not-an-image.png"
    bad_file.write_bytes(b"this is not an image")

    output_path = tmp_path / "out.pdf"
    output_path.write_text("important pre-existing content")

    with pytest.raises(ConversionFailedError):
        PngImagesToPdfMerger().merge([SAMPLE_PNG, bad_file], output_path)

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_import_failure_surfaces_as_converter_unavailable(monkeypatch, tmp_path):
    import sys

    monkeypatch.setitem(sys.modules, "PIL", None)

    with pytest.raises(ConverterUnavailableError):
        PngImagesToPdfMerger().merge([SAMPLE_PNG, SAMPLE_PNG], tmp_path / "out.pdf")
