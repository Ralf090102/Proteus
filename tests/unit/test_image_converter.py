"""Unit tests for the Pillow-backed image converters' availability/
missing-Pillow handling — simulates PIL being absent via sys.modules, so
no real Pillow install is needed and these always run regardless of
whether the optional `images` extra is installed in this environment.
Real-conversion tests (which do need real Pillow) live in
test_image_converter_real.py, a separate module so pytest.importorskip
there can skip that whole file cleanly without affecting these."""

from __future__ import annotations

import sys

import pytest

from proteus.converters.image import PngToJpgConverter
from proteus.core.converter import ConversionOptions
from proteus.core.errors import ConverterUnavailableError


def test_is_available_false_when_pillow_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)
    assert PngToJpgConverter().is_available() is False


def test_convert_raises_converter_unavailable_when_pillow_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "PIL", None)

    with pytest.raises(ConverterUnavailableError, match=r"uv tool install \.\[images\]"):
        PngToJpgConverter().convert(
            tmp_path / "in.png", tmp_path / "out.jpg", ConversionOptions()
        )


def test_tool_checks_reports_extra_kind_when_pillow_missing(monkeypatch):
    from proteus.core.converter import ToolCheck
    from proteus.core.dependencies import AvailabilityStatus

    monkeypatch.setitem(sys.modules, "PIL", None)

    checks = PngToJpgConverter().tool_checks()

    assert checks == (ToolCheck("pillow", AvailabilityStatus(False, None, "not-found"), "extra"),)
