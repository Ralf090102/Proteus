"""Unit-test-wide fixtures.

FakeConverter is a minimal Converter double used across registry/CLI unit
tests — it never touches the filesystem or shells out, so tests stay fast
and don't depend on any real converter being registered (none lands until
Phase 3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.core.converter import ConversionOptions, ConversionResult, Converter


class FakeConverter(Converter):
    from_ext = "fake"
    to_ext = "fake2"

    def __init__(self, *, available: bool = True) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        return ConversionResult(output_path=output_path)


@pytest.fixture
def fake_converter() -> FakeConverter:
    return FakeConverter()
