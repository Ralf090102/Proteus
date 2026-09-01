"""Proves the Converter ABC contract with a trivial dummy converter."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.core.converter import ConversionOptions, ConversionResult, Converter


class DummyConverter(Converter):
    from_ext = "dummy"
    to_ext = "dummy2"

    def is_available(self) -> bool:
        return True

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        return ConversionResult(output_path=output_path)


def test_cannot_instantiate_converter_directly():
    with pytest.raises(TypeError):
        Converter()  # type: ignore[abstract]


def test_dummy_converter_reports_available_and_converts():
    converter = DummyConverter()
    assert converter.is_available() is True
    result = converter.convert(Path("in.dummy"), Path("out.dummy2"), ConversionOptions())
    assert result.output_path == Path("out.dummy2")


def test_conversion_options_reject_unknown_fields():
    with pytest.raises(Exception):
        ConversionOptions(extra_field="nope")  # type: ignore[call-arg]


def test_conversion_result_reject_unknown_fields():
    with pytest.raises(Exception):
        ConversionResult(output_path=Path("out.pdf"), extra_field="nope")  # type: ignore[call-arg]
