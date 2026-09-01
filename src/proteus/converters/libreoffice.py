"""LibreOffice-headless-backed converter: docx -> pdf.

Shells out to `soffice --headless --convert-to pdf --outdir <dir> <input>`
inside a fresh, isolated user profile per call (see
core/subprocess_utils.isolated_libreoffice_profile) to avoid profile-lock
contention if multiple calls happen back to back.
"""

from __future__ import annotations

from pathlib import Path

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ensure_output_created,
)
from proteus.core.dependencies import find_tool
from proteus.core.errors import ConversionFailedError, ConverterUnavailableError
from proteus.core.subprocess_utils import isolated_libreoffice_profile, run_subprocess

SOFFICE_BIN = "soffice"
SOFFICE_ENV_VAR = "PROTEUS_SOFFICE_PATH"


class LibreOfficeConverter(Converter):
    from_ext = "docx"
    to_ext = "pdf"

    def is_available(self) -> bool:
        return find_tool(SOFFICE_BIN, env_var=SOFFICE_ENV_VAR).available

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        status = find_tool(SOFFICE_BIN, env_var=SOFFICE_ENV_VAR)
        if not status.available:
            raise ConverterUnavailableError(
                f"LibreOffice ({SOFFICE_BIN}) not found. Install it to convert "
                f"{self.from_ext}->{self.to_ext}."
            )

        with isolated_libreoffice_profile() as profile_arg:
            run_subprocess(
                [
                    str(status.path),
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
        ensure_output_created(produced, "LibreOffice")

        if produced != output_path:
            try:
                produced.replace(output_path)
            except OSError as e:
                raise ConversionFailedError(
                    f"LibreOffice produced {produced} but couldn't move it to "
                    f"{output_path} (destination may be open elsewhere): {e}"
                ) from e

        return ConversionResult(output_path=output_path)
