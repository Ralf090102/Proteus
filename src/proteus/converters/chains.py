"""Generic chain-of-converters engine.

A ChainConverter runs a fixed sequence of Converter steps end to end,
writing each intermediate result to a temp file and feeding it into the
next step. Concrete chains are thin subclasses that set `steps` (plus
from_ext/to_ext for the overall pair) — e.g. md -> pdf as md -> docx
(Pandoc) -> pdf (LibreOffice), reusing those converters unchanged.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import ClassVar

from proteus.converters.libreoffice import LibreOfficeConverter
from proteus.converters.pandoc import MarkdownToDocxConverter
from proteus.core.converter import ConversionOptions, ConversionResult, Converter, ToolCheck
from proteus.core.errors import ConversionFailedError, ProteusError


class ChainConverter(Converter):
    """Base class for a converter built out of other converters run in
    sequence. Subclasses set `steps`; from_ext/to_ext describe the overall
    pair (the first step's from_ext and the last step's to_ext)."""

    steps: ClassVar[tuple[type[Converter], ...]]

    def is_available(self) -> bool:
        return all(step_class().is_available() for step_class in self.steps)

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        # Surfaces every step's tools individually (e.g. both Pandoc and
        # LibreOffice for md->pdf) so `doctor` can say *which* underlying
        # backend is missing, not just that the chain as a whole is not.
        return tuple(
            check for step_class in self.steps for check in step_class().tool_checks()
        )

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        try:
            with tempfile.TemporaryDirectory(prefix="proteus-chain-") as tmp_dir:
                current_input = input_path
                last_index = len(self.steps) - 1
                for i, step_class in enumerate(self.steps):
                    is_last = i == last_index
                    step_output = (
                        output_path
                        if is_last
                        else Path(tmp_dir) / f"step{i}.{step_class.to_ext}"
                    )
                    try:
                        step_class().convert(current_input, step_output, options)
                    except ProteusError as e:
                        raise ConversionFailedError(
                            f"Chain step {i + 1}/{len(self.steps)} "
                            f"({step_class.__name__}, "
                            f"{step_class.from_ext}->{step_class.to_ext}) failed: {e}"
                        ) from e
                    current_input = step_output
        except OSError as e:
            # Only reachable for a failure setting up the temp staging
            # dir itself (e.g. disk full) — a step's own OSErrors are
            # already converters' responsibility to wrap as ProteusError.
            raise ConversionFailedError(
                f"Could not set up a temporary working directory for the "
                f"conversion chain: {e}"
            ) from e

        return ConversionResult(output_path=output_path)


class MarkdownToPdfChainConverter(ChainConverter):
    from_ext = "md"
    to_ext = "pdf"
    steps = (MarkdownToDocxConverter, LibreOfficeConverter)
