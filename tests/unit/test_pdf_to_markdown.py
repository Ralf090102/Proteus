"""Unit tests for PdfToMarkdownConverter's availability/missing-pymupdf4llm
handling — simulates pymupdf4llm being absent via sys.modules, so no real
install is needed and these always run regardless of whether the optional
`markdown` extra is installed in this environment. Real-conversion tests
(which do need pymupdf4llm) live in test_pdf_to_markdown_real.py, a
separate module so pytest.importorskip there can skip that whole file
cleanly without affecting these."""

from __future__ import annotations

import builtins
import sys

import pytest

from proteus.converters.pdf_extract import PdfToMarkdownConverter, _current_pymupdf_message_stream
from proteus.core.converter import ConversionOptions, ToolCheck
from proteus.core.dependencies import AvailabilityStatus
from proteus.core.errors import ConverterUnavailableError


def test_is_available_false_when_pymupdf4llm_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)
    assert PdfToMarkdownConverter().is_available() is False


def test_convert_raises_converter_unavailable_when_pymupdf4llm_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)

    with pytest.raises(ConverterUnavailableError, match=r"uv tool install \.\[markdown\]"):
        PdfToMarkdownConverter().convert(
            tmp_path / "in.pdf", tmp_path / "out.md", ConversionOptions()
        )


def test_tool_checks_reports_extra_kind_when_pymupdf4llm_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)

    checks = PdfToMarkdownConverter().tool_checks()

    assert checks == (
        ToolCheck("pymupdf4llm", AvailabilityStatus(False, None, "not-found"), "extra"),
    )


def _break_pymupdf4llm_import(monkeypatch, exc: Exception) -> None:
    # sys.modules["pymupdf4llm"] = None only forces ImportError
    # specifically — simulating a genuinely broken install (not just a
    # missing one, e.g. one of pymupdf4llm's own real transitive deps
    # like onnxruntime failing to load) needs `import pymupdf4llm` to
    # raise something else entirely, which means patching the import
    # machinery itself.
    monkeypatch.delitem(sys.modules, "pymupdf4llm", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pymupdf4llm":
            raise exc
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_is_available_false_when_pymupdf4llm_import_raises_non_import_error(monkeypatch):
    # Broader-than-ImportError coverage: pymupdf4llm pulls in real
    # transitive packages (pymupdf-layout, onnxruntime, networkx), any of
    # which failing could raise something other than ImportError —
    # is_available() must still return False, not crash doctor()/
    # list-formats() for every other pair too.
    _break_pymupdf4llm_import(monkeypatch, OSError("simulated broken native extension"))
    assert PdfToMarkdownConverter().is_available() is False


def test_convert_raises_converter_unavailable_when_import_raises_non_import_error(
    monkeypatch, tmp_path
):
    _break_pymupdf4llm_import(monkeypatch, OSError("simulated broken native extension"))

    with pytest.raises(ConverterUnavailableError, match=r"uv tool install \.\[markdown\]"):
        PdfToMarkdownConverter().convert(
            tmp_path / "in.pdf", tmp_path / "out.md", ConversionOptions()
        )


def test_tool_checks_reports_not_found_when_import_raises_non_import_error(monkeypatch):
    _break_pymupdf4llm_import(monkeypatch, OSError("simulated broken native extension"))

    checks = PdfToMarkdownConverter().tool_checks()

    assert checks == (
        ToolCheck("pymupdf4llm", AvailabilityStatus(False, None, "not-found"), "extra"),
    )


# --- _current_pymupdf_message_stream (the private-attribute read used to
# save/restore pymupdf's message sink around a pdf->md conversion) ---
#
# Tested against fake objects, not a real pymupdf install, so the
# AttributeError-degrades-to-None behavior is exercised in isolation —
# deleting the real attribute off a live pymupdf module breaks pymupdf's
# own internals (confirmed directly), which isn't what this function's
# degradation path is meant to guard against.


def test_current_pymupdf_message_stream_returns_none_when_attribute_missing():
    class FakePymupdfWithoutAttr:
        pass

    assert _current_pymupdf_message_stream(FakePymupdfWithoutAttr()) is None


def test_current_pymupdf_message_stream_returns_value_when_present():
    class FakePymupdfWithAttr:
        _g_out_message = "sentinel-stream"

    assert _current_pymupdf_message_stream(FakePymupdfWithAttr()) == "sentinel-stream"
