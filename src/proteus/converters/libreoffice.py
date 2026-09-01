"""LibreOffice-headless-backed converter: docx -> pdf.

Shells out to `soffice --headless --convert-to pdf --outdir <dir> <input>`
inside a fresh, isolated user profile per call (see
core/subprocess_utils.isolated_libreoffice_profile) to avoid profile-lock
contention if multiple calls happen back to back.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from proteus.core.converter import ConversionOptions, ConversionResult, Converter
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError
from proteus.core.subprocess_utils import isolated_libreoffice_profile, run_subprocess

SOFFICE_BIN = "soffice"


class LibreOfficeConverter(Converter):
    from_ext = "docx"
    to_ext = "pdf"

    def is_available(self) -> bool:
        return shutil.which(SOFFICE_BIN) is not None

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        if not self.is_available():
            raise ConverterUnavailableError(
                f"LibreOffice ({SOFFICE_BIN}) not found on PATH. Install it to convert "
                f"{self.from_ext}->{self.to_ext}."
            )

        with isolated_libreoffice_profile() as profile_arg:
            run_subprocess(
                [
                    SOFFICE_BIN,
                    "--headless",
                    profile_arg,
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(output_path.parent),
                    str(input_path),
                ]
            )

        # LibreOffice always names its output <input-stem>.pdf inside
        # --outdir, regardless of the caller's requested filename. Verify
        # it actually landed — soffice can exit 0 without producing output
        # under profile-lock contention or on some malformed inputs — then
        # move it into place if that doesn't already match output_path.
        produced = output_path.parent / f"{input_path.stem}.pdf"
        if not produced.exists():
            raise ConversionFailedError(
                f"LibreOffice reported success but {produced} wasn't created"
            )

        if produced != output_path:
            try:
                produced.replace(output_path)
            except OSError as e:
                raise ConversionFailedError(
                    f"LibreOffice produced {produced} but couldn't move it to "
                    f"{output_path} (destination may be open elsewhere): {e}"
                ) from e

        return ConversionResult(output_path=output_path)
