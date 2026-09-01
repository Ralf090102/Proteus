"""Proteus's own error hierarchy.

All errors a Converter.convert() implementation raises should subclass
ProteusError (not a bare Exception), so callers can handle conversion
failures uniformly regardless of which backend a given converter uses
under the hood.
"""

from __future__ import annotations


class ProteusError(Exception):
    """Base class for all Proteus-raised errors."""


class UnknownConversionError(ProteusError):
    """The requested (from_ext, to_ext) pair isn't registered in
    CONVERTER_REGISTRY."""


class ConverterUnavailableError(ProteusError):
    """A converter's required external tool (e.g. LibreOffice, Pandoc)
    isn't installed or isn't on PATH."""


class ConversionFailedError(ProteusError):
    """The converter's backend ran but the conversion itself failed
    (subprocess non-zero exit, malformed output, etc.)."""
