"""Unit tests for the generic ChainConverter engine, using small local
dummy steps — not real converters, so no external tool is needed here."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.chains import ChainConverter, MarkdownToPdfChainConverter
from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.converters.pandoc import MarkdownToDocxConverter
from proteus.core.converter import ConversionOptions, ConversionResult, Converter


class _StepA(Converter):
    from_ext = "fake"
    to_ext = "mid"
    available = True

    def is_available(self) -> bool:
        return self.available

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        output_path.write_text(f"stepA<-{input_path.read_text()}")
        return ConversionResult(output_path=output_path)


class _StepB(Converter):
    from_ext = "mid"
    to_ext = "final"
    available = True

    def is_available(self) -> bool:
        return self.available

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        output_path.write_text(f"stepB<-{input_path.read_text()}")
        return ConversionResult(output_path=output_path)


class _FailingStep(Converter):
    from_ext = "mid"
    to_ext = "final"

    def is_available(self) -> bool:
        return True

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        raise RuntimeError("boom")


class _TwoStepChain(ChainConverter):
    from_ext = "fake"
    to_ext = "final"
    steps = (_StepA, _StepB)


def test_chain_runs_steps_in_order_and_writes_final_output(tmp_path):
    input_path = tmp_path / "in.fake"
    input_path.write_text("original")
    output_path = tmp_path / "out.final"

    result = _TwoStepChain().convert(input_path, output_path, ConversionOptions())

    assert result.output_path == output_path
    assert output_path.read_text() == "stepB<-stepA<-original"


def test_chain_is_available_only_if_every_step_is():
    _StepA.available = True
    _StepB.available = True
    assert _TwoStepChain().is_available() is True

    _StepB.available = False
    try:
        assert _TwoStepChain().is_available() is False
    finally:
        _StepB.available = True  # don't leak state into other tests


def test_chain_propagates_a_mid_chain_step_failure(tmp_path):
    class _FailingChain(ChainConverter):
        from_ext = "fake"
        to_ext = "final"
        steps = (_StepA, _FailingStep)

    input_path = tmp_path / "in.fake"
    input_path.write_text("original")

    with pytest.raises(RuntimeError):
        _FailingChain().convert(input_path, tmp_path / "out.final", ConversionOptions())


def test_markdown_to_pdf_chain_availability_reflects_both_steps(monkeypatch):
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.converters import pandoc as pandoc_module
    from proteus.core.dependencies import AvailabilityStatus

    available = AvailabilityStatus(True, Path("/usr/bin/tool"), "path")
    unavailable = AvailabilityStatus(False, None, "not-found")

    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: available)
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: available)
    assert MarkdownToPdfChainConverter().is_available() is True

    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: unavailable)
    assert MarkdownToPdfChainConverter().is_available() is False


def test_markdown_to_pdf_chain_steps_are_pandoc_then_libreoffice():
    assert MarkdownToPdfChainConverter.steps == (MarkdownToDocxConverter, LibreOfficeConverter)
