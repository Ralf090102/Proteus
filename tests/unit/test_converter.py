"""Proves the Converter ABC contract with a trivial dummy converter."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    atomic_write,
    ensure_output_created,
)
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError


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


# --- atomic_write() ---
#
# Direct tests for the shared write-to-temp/verify/replace-in mechanics
# every Converter/Merger that writes its own output file now routes
# through (converters/image.py, pdf_extract.py, pandoc.py, merge.py) —
# each of those keeps its own "doesn't destroy pre-existing output"
# regression test too (pinning that it's actually wired to atomic_write,
# not just that the mechanism works), so these test the mechanism itself
# in isolation rather than duplicating that per-converter coverage.


def test_atomic_write_writes_via_write_fn_and_returns_conversion_result(tmp_path):
    output_path = tmp_path / "out.txt"

    def write(tmp_output: Path) -> None:
        tmp_output.write_text("hello")

    result = atomic_write(output_path, "SomeBackend", write)

    assert result == ConversionResult(output_path=output_path)
    assert output_path.read_text() == "hello"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_atomic_write_propagates_conversion_failed_error_from_write_fn_unchanged(tmp_path):
    def write(tmp_output: Path) -> None:
        raise ConversionFailedError("SomeBackend failed to do the specific thing")

    with pytest.raises(ConversionFailedError, match="failed to do the specific thing"):
        atomic_write(tmp_path / "out.txt", "SomeBackend", write)


def test_atomic_write_propagates_converter_unavailable_error_from_write_fn_unchanged(tmp_path):
    # Regression: the safety net below must only catch non-ProteusError
    # exceptions — a write_fn that raises ConverterUnavailableError (e.g.
    # pandoc.py's run_subprocess()) must not have it silently reclassified
    # into a generic ConversionFailedError.
    def write(tmp_output: Path) -> None:
        raise ConverterUnavailableError("some-tool not found")

    with pytest.raises(ConverterUnavailableError, match="some-tool not found"):
        atomic_write(tmp_path / "out.txt", "SomeBackend", write)


def test_atomic_write_wraps_a_write_fn_that_forgot_to_raise_conversionfailederror(tmp_path):
    # Safety net only — every real write_fn is expected to raise
    # ConversionFailedError itself with its own wording; this covers the
    # "forgot to wrap" bug case so a bare exception still can't leak past
    # the "converters only ever raise ProteusError" contract.
    def write(tmp_output: Path) -> None:
        raise ValueError("oops, forgot to wrap this")

    with pytest.raises(ConversionFailedError, match="SomeBackend"):
        atomic_write(tmp_path / "out.txt", "SomeBackend", write)


def test_atomic_write_does_not_destroy_pre_existing_output_on_write_fn_failure(tmp_path):
    output_path = tmp_path / "out.txt"
    output_path.write_text("important pre-existing content")

    def write(tmp_output: Path) -> None:
        raise ConversionFailedError("boom")

    with pytest.raises(ConversionFailedError):
        atomic_write(output_path, "SomeBackend", write)

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []


def test_atomic_write_raises_if_write_fn_produces_an_empty_file(tmp_path):
    def write(tmp_output: Path) -> None:
        tmp_output.write_bytes(b"")  # reports success but writes nothing

    with pytest.raises(ConversionFailedError, match="is empty"):
        atomic_write(tmp_path / "out.txt", "SomeBackend", write)
