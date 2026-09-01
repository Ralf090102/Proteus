"""Tests for the conversion-pair registry — fully known spec, no external unknowns."""

from __future__ import annotations

import pytest

from proteus.converters.chains import MarkdownToPdfChainConverter
from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.converters.pandoc import DocxToMarkdownConverter, MarkdownToDocxConverter
from proteus.core.errors import UnknownConversionError
from proteus.core.registry import CONVERTER_REGISTRY, get_converter


def test_docx_to_pdf_registered_to_libreoffice_converter():
    assert CONVERTER_REGISTRY[("docx", "pdf")] is LibreOfficeConverter


def test_docx_to_md_registered_to_pandoc_converter():
    assert CONVERTER_REGISTRY[("docx", "md")] is DocxToMarkdownConverter


def test_md_to_docx_registered_to_pandoc_converter():
    assert CONVERTER_REGISTRY[("md", "docx")] is MarkdownToDocxConverter


def test_md_to_pdf_registered_to_chain_converter():
    assert CONVERTER_REGISTRY[("md", "pdf")] is MarkdownToPdfChainConverter


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
        get_converter("pdf", "docx")
