"""Tests for the conversion-pair registry — fully known spec, no external unknowns."""

from __future__ import annotations

import pytest

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
from proteus.core.errors import UnknownConversionError
from proteus.core.registry import (
    CONVERTER_REGISTRY,
    MERGE_REGISTRY,
    get_converter,
    get_merger,
)


def test_docx_to_pdf_registered_to_libreoffice_converter():
    assert CONVERTER_REGISTRY[("docx", "pdf")] is LibreOfficeConverter


def test_pptx_to_pdf_registered_to_pptx_converter():
    assert CONVERTER_REGISTRY[("pptx", "pdf")] is PptxToPdfConverter


def test_ppt_to_pdf_registered_to_ppt_converter():
    assert CONVERTER_REGISTRY[("ppt", "pdf")] is PptToPdfConverter


def test_docx_to_md_registered_to_pandoc_converter():
    assert CONVERTER_REGISTRY[("docx", "md")] is DocxToMarkdownConverter


def test_md_to_docx_registered_to_pandoc_converter():
    assert CONVERTER_REGISTRY[("md", "docx")] is MarkdownToDocxConverter


def test_md_to_pdf_registered_to_chain_converter():
    assert CONVERTER_REGISTRY[("md", "pdf")] is MarkdownToPdfChainConverter


def test_pdf_to_docx_registered_to_pdf2docx_converter():
    assert CONVERTER_REGISTRY[("pdf", "docx")] is Pdf2DocxConverter


def test_pdf_to_txt_registered_to_pymupdf_converter():
    assert CONVERTER_REGISTRY[("pdf", "txt")] is PyMuPdfTextExtractConverter


def test_pdf_to_md_registered_to_pdf_to_markdown_converter():
    assert CONVERTER_REGISTRY[("pdf", "md")] is PdfToMarkdownConverter


def test_png_to_jpg_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("png", "jpg")] is PngToJpgConverter


def test_jpg_to_png_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("jpg", "png")] is JpgToPngConverter


def test_webp_to_jpg_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("webp", "jpg")] is WebpToJpgConverter


def test_webp_to_png_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("webp", "png")] is WebpToPngConverter


def test_jpg_to_webp_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("jpg", "webp")] is JpgToWebpConverter


def test_png_to_webp_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("png", "webp")] is PngToWebpConverter


def test_png_to_pdf_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("png", "pdf")] is PngToPdfConverter


def test_jpg_to_pdf_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("jpg", "pdf")] is JpgToPdfConverter


def test_webp_to_pdf_registered_to_image_converter():
    assert CONVERTER_REGISTRY[("webp", "pdf")] is WebpToPdfConverter


def test_get_converter_known_pair_constructs_instance(fake_converter):
    fake_class = type(fake_converter)
    registry = {(fake_class.from_ext, fake_class.to_ext): fake_class}
    converter = get_converter("fake", "fake2", registry=registry)
    assert isinstance(converter, fake_class)


def test_get_converter_unknown_pair_raises_with_attempted_and_known_pairs_listed(fake_converter):
    fake_class = type(fake_converter)
    registry = {(fake_class.from_ext, fake_class.to_ext): fake_class}
    with pytest.raises(UnknownConversionError) as exc_info:
        get_converter("docx", "pdf", registry=registry)
    message = str(exc_info.value)
    assert "docx" in message
    assert "pdf" in message
    assert "fake->fake2" in message


def test_get_converter_empty_registry_raises_with_none_registered_message():
    with pytest.raises(UnknownConversionError) as exc_info:
        get_converter("docx", "pdf", registry={})
    assert "none registered yet" in str(exc_info.value)


def test_get_converter_against_real_registry_constructs_libreoffice_converter():
    converter = get_converter("docx", "pdf")
    assert isinstance(converter, LibreOfficeConverter)


def test_get_converter_against_real_registry_unknown_pair_raises():
    with pytest.raises(UnknownConversionError):
        get_converter("txt", "pdf")


def test_pdf_registered_to_pdf_merger():
    assert MERGE_REGISTRY["pdf"] is PdfMerger


def test_md_registered_to_markdown_merger():
    assert MERGE_REGISTRY["md"] is MarkdownMerger


def test_txt_registered_to_text_merger():
    assert MERGE_REGISTRY["txt"] is TextMerger


def test_png_registered_to_png_images_to_pdf_merger():
    assert MERGE_REGISTRY["png"] is PngImagesToPdfMerger


def test_jpg_registered_to_jpg_images_to_pdf_merger():
    assert MERGE_REGISTRY["jpg"] is JpgImagesToPdfMerger


def test_webp_registered_to_webp_images_to_pdf_merger():
    assert MERGE_REGISTRY["webp"] is WebpImagesToPdfMerger


def test_get_merger_known_extension_constructs_instance():
    registry = {"dummy": PdfMerger}
    merger = get_merger("dummy", registry=registry)
    assert isinstance(merger, PdfMerger)


def test_get_merger_unknown_extension_raises_with_attempted_and_known_extensions_listed():
    registry = {"pdf": PdfMerger, "md": MarkdownMerger}
    with pytest.raises(UnknownConversionError) as exc_info:
        get_merger("docx", registry=registry)
    message = str(exc_info.value)
    assert "docx" in message
    assert "pdf" in message
    assert "md" in message


def test_get_merger_empty_registry_raises_with_none_registered_message():
    with pytest.raises(UnknownConversionError) as exc_info:
        get_merger("pdf", registry={})
    assert "none registered yet" in str(exc_info.value)


def test_get_merger_against_real_registry_constructs_pdf_merger():
    merger = get_merger("pdf")
    assert isinstance(merger, PdfMerger)


def test_get_merger_against_real_registry_unknown_extension_raises():
    with pytest.raises(UnknownConversionError):
        get_merger("docx")


def test_get_merger_normalizes_casing():
    registry = {"pdf": PdfMerger}
    merger = get_merger("PDF", registry=registry)
    assert isinstance(merger, PdfMerger)


def test_get_converter_normalizes_casing(fake_converter):
    # converter.py's own docstring says extensions are "normalized once
    # at the CLI/registry boundary" — get_converter() should hold that
    # invariant itself rather than trusting every caller to lowercase
    # first, so a direct/library caller bypassing the CLI still resolves.
    fake_class = type(fake_converter)
    registry = {(fake_class.from_ext, fake_class.to_ext): fake_class}
    converter = get_converter("FAKE", "FAKE2", registry=registry)
    assert isinstance(converter, fake_class)
