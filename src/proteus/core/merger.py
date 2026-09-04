"""Merger contract every merge backend implements — parallel to
core/converter.py's Converter, for v3's "combine 2+ same-type files into
one" feature (Send To, not the right-click convert menu; see
windows/sendto.py).

Where a Converter maps one (from_ext, to_ext) pair to one input file, a
Merger maps one shared source extension to N input files and one output
file. from_ext is also MERGE_REGISTRY's lookup key (core/registry.py);
to_ext is usually the same extension but differs for ImagesToPdfMerger
(from_ext is whichever of png/jpg/webp was selected, to_ext is always
"pdf").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from proteus.core.converter import ConversionResult, ToolCheck


class Merger(ABC):
    """Base contract for combining 2+ same-extension files into one."""

    from_ext: ClassVar[str]
    to_ext: ClassVar[str]

    @abstractmethod
    def is_available(self) -> bool:
        """Same contract as Converter.is_available() — whether this
        merger's required dependency (external tool or Python package) is
        present on this machine."""
        raise NotImplementedError

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        """Same contract as Converter.tool_checks() — empty by default for
        a merger with no external dependency to report."""
        return ()

    @abstractmethod
    def merge(self, input_paths: list[Path], output_path: Path) -> ConversionResult:
        """Combine input_paths (already validated as 2+ files sharing
        from_ext, already ordered by the caller) into one file at
        output_path.

        Implementations must raise a ProteusError subclass (see
        core/errors.py) on any failure, never a bare Exception, and must
        leave no partial output behind on failure — same atomic-write
        discipline every existing Converter follows.
        """
        raise NotImplementedError
