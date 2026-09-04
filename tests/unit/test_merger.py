"""Proves the Merger ABC contract with a trivial dummy merger — mirrors
test_converter.py's DummyConverter."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.core.converter import ConversionResult
from proteus.core.merger import Merger


class DummyMerger(Merger):
    from_ext = "dummy"
    to_ext = "dummy"

    def is_available(self) -> bool:
        return True

    def merge(self, input_paths: list[Path], output_path: Path) -> ConversionResult:
        return ConversionResult(output_path=output_path)


def test_cannot_instantiate_merger_directly():
    with pytest.raises(TypeError):
        Merger()  # type: ignore[abstract]


def test_dummy_merger_reports_available_and_merges():
    merger = DummyMerger()
    assert merger.is_available() is True
    result = merger.merge([Path("a.dummy"), Path("b.dummy")], Path("out.dummy"))
    assert result.output_path == Path("out.dummy")


def test_tool_checks_defaults_to_empty_tuple():
    assert DummyMerger().tool_checks() == ()
