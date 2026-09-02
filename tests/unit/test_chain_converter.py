"""Unit tests for the generic ChainConverter engine, using small local
dummy steps — not real converters, so no external tool is needed here."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.chains import ChainConverter, MarkdownToPdfChainConverter
from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.converters.pandoc import MarkdownToDocxConverter
from proteus.core.converter import ConversionOptions, ConversionResult, Converter
from proteus.core.errors import ConversionFailedError


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


def test_chain_wraps_a_real_step_failure_with_step_context(tmp_path):
    # Unlike _FailingStep above (a raw RuntimeError, used to prove generic
    # exception propagation), real converters raise ProteusError per the
    # documented contract — those should be wrapped so the message names
    # which step/converter in the chain actually failed.
    class _FailingProteusStep(Converter):
        from_ext = "mid"
        to_ext = "final"

        def is_available(self) -> bool:
            return True

        def convert(
            self, input_path: Path, output_path: Path, options: ConversionOptions
        ) -> ConversionResult:
            raise ConversionFailedError("underlying tool exploded")

    class _FailingChain(ChainConverter):
        from_ext = "fake"
        to_ext = "final"
        steps = (_StepA, _FailingProteusStep)

    input_path = tmp_path / "in.fake"
    input_path.write_text("original")

    with pytest.raises(ConversionFailedError, match="step 2/2") as exc_info:
        _FailingChain().convert(input_path, tmp_path / "out.final", ConversionOptions())

    message = str(exc_info.value)
    assert "_FailingProteusStep" in message
    assert "underlying tool exploded" in message


def test_chain_wraps_temp_dir_setup_failure(monkeypatch, tmp_path):
    from proteus.converters import chains as chains_module

    def raise_oserror(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(chains_module.tempfile, "TemporaryDirectory", raise_oserror)

    input_path = tmp_path / "in.fake"
    input_path.write_text("original")

    with pytest.raises(ConversionFailedError, match="temporary working directory"):
        _TwoStepChain().convert(input_path, tmp_path / "out.final", ConversionOptions())


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


def test_markdown_to_pdf_chain_tool_checks_surfaces_both_steps(monkeypatch):
    # Regression target for `proteus doctor`: a chain's tool_checks() must
    # expose *each* underlying tool individually (not just an aggregate
    # bool) so an unavailable md->pdf tells you whether Pandoc or
    # LibreOffice (or both) is the actual problem.
    from proteus.converters import libreoffice as libreoffice_module
    from proteus.converters import pandoc as pandoc_module
    from proteus.core.converter import ToolCheck
    from proteus.core.dependencies import AvailabilityStatus

    pandoc_status = AvailabilityStatus(True, Path("/usr/bin/pandoc"), "path")
    soffice_status = AvailabilityStatus(False, None, "not-found")

    monkeypatch.setattr(pandoc_module, "find_tool", lambda *a, **k: pandoc_status)
    monkeypatch.setattr(libreoffice_module, "find_tool", lambda *a, **k: soffice_status)

    checks = MarkdownToPdfChainConverter().tool_checks()

    assert checks == (
        ToolCheck(pandoc_module.PANDOC_BIN, pandoc_status),
        ToolCheck(libreoffice_module.SOFFICE_BIN, soffice_status),
    )
