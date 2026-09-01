"""Tests for the conversion-pair registry — fully known spec, no external unknowns."""

from __future__ import annotations

import pytest

from proteus.core.errors import UnknownConversionError
from proteus.core.registry import CONVERTER_REGISTRY, get_converter


def test_converter_registry_starts_empty():
    # Real converters land in Phase 3 — asserting this stays true until
    # then catches an accidental early registration.
    assert CONVERTER_REGISTRY == {}


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


def test_get_converter_against_real_registry_currently_raises():
    # CONVERTER_REGISTRY is empty until Phase 3 — the default-arg lookup
    # path should behave identically to an explicit empty registry.
    with pytest.raises(UnknownConversionError):
        get_converter("docx", "pdf")
