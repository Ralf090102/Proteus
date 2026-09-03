"""Unit tests for the Pillow-backed image converters' availability/
missing-Pillow handling — simulates PIL being absent via sys.modules, so
no real Pillow install is needed and these always run regardless of
whether the optional `images` extra is installed in this environment.
Real-conversion tests (which do need real Pillow) live in
test_image_converter_real.py, a separate module so pytest.importorskip
there can skip that whole file cleanly without affecting these."""

from __future__ import annotations

import builtins
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


def _break_pil_import(monkeypatch, exc: Exception) -> None:
    # sys.modules["PIL"] = None only forces ImportError specifically —
    # simulating a genuinely broken install (not just a missing one)
    # needs `import PIL` to raise something else entirely, which means
    # patching the import machinery itself.
    monkeypatch.delitem(sys.modules, "PIL", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PIL":
            raise exc
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_is_available_false_when_pillow_import_raises_non_import_error(monkeypatch):
    # Broader-than-ImportError coverage: a genuinely broken install (e.g.
    # a corrupted native extension) can fail import with something else
    # entirely — is_available() must still return False, not let the
    # exception propagate and crash doctor()/list-formats() for every
    # other registered pair too.
    _break_pil_import(monkeypatch, OSError("simulated broken native extension"))
    assert PngToJpgConverter().is_available() is False


def test_tool_checks_reports_not_found_when_pillow_import_raises_non_import_error(monkeypatch):
    from proteus.core.converter import ToolCheck
    from proteus.core.dependencies import AvailabilityStatus

    _break_pil_import(monkeypatch, OSError("simulated broken native extension"))

    checks = PngToJpgConverter().tool_checks()

    assert checks == (ToolCheck("pillow", AvailabilityStatus(False, None, "not-found"), "extra"),)
