"""Proves the Converter ABC contract with a trivial dummy converter."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ensure_output_created,
)
from proteus.core.errors import ConversionFailedError


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


def test_ensure_output_created_raises_if_missing(tmp_path):
    with pytest.raises(ConversionFailedError, match="wasn't created"):
        ensure_output_created(tmp_path / "missing.pdf", "SomeBackend")


def test_ensure_output_created_raises_if_empty(tmp_path):
    # A backend reporting success (exit 0) doesn't guarantee it actually
    # wrote real content — e.g. disk-full-mid-write can leave a 0-byte
    # file behind while still exiting cleanly.
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")

    with pytest.raises(ConversionFailedError, match="is empty"):
        ensure_output_created(empty_file, "SomeBackend")


def test_ensure_output_created_passes_for_non_empty_file(tmp_path):
    real_file = tmp_path / "real.pdf"
    real_file.write_bytes(b"%PDF-fake")

    ensure_output_created(real_file, "SomeBackend")  # must not raise
