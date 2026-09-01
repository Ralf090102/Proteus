"""LibreOffice-headless-backed converter: docx -> pdf.

Shells out to `soffice --headless --convert-to pdf --outdir <dir> <input>`
inside a fresh, isolated user profile per call (see
core/subprocess_utils.isolated_libreoffice_profile) to avoid profile-lock
contention if multiple calls happen back to back.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from proteus.core.converter import (
    ConversionOptions,
    ConversionResult,
    Converter,
    ToolCheck,
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

    def tool_checks(self) -> tuple[ToolCheck, ...]:
        return (ToolCheck(SOFFICE_BIN, find_tool(SOFFICE_BIN, env_var=SOFFICE_ENV_VAR)),)

    def convert(
        self, input_path: Path, output_path: Path, options: ConversionOptions
    ) -> ConversionResult:
        status = find_tool(SOFFICE_BIN, env_var=SOFFICE_ENV_VAR)
        if not status.available:
            raise ConverterUnavailableError(
                f"LibreOffice ({SOFFICE_BIN}) not found. Install it to convert "
                f"{self.from_ext}->{self.to_ext}."
            )

        # LibreOffice always names its output <input-stem>.pdf and writes
        # it directly into --outdir, unconditionally overwriting anything
        # already there under that name — pointing --outdir at an
        # isolated temp dir (rather than output_path.parent, the real
        # destination) means that can never collide with and silently
        # clobber an unrelated file that happens to share the input's
        # stem. The only write into the real destination is the final
        # move below, and only at the exact path the caller asked for.
        with tempfile.TemporaryDirectory(prefix="proteus-soffice-out-") as tmp_outdir:
            with isolated_libreoffice_profile() as profile_arg:
                run_subprocess(
                    [
                        str(status.path),
                        "--headless",
                        profile_arg,
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        tmp_outdir,
                        str(input_path),
                    ]
                )

            # Verify it actually landed — soffice can exit 0 without
            # producing output under profile-lock contention or on some
            # malformed inputs.
            produced = Path(tmp_outdir) / f"{input_path.stem}.pdf"
            ensure_output_created(produced, "LibreOffice")

            try:
                # shutil.move(), not Path.replace()/os.replace(): the temp
                # staging dir and the real destination can be on different
                # drives (the common case for this repo — %TEMP% is on C:,
                # the project is on D:), and os.replace()'s MoveFileExW
                # call has no MOVEFILE_COPY_ALLOWED fallback for that —
                # it fails outright with WinError 17 cross-drive.
                # shutil.move() falls back to copy+delete automatically.
                shutil.move(str(produced), str(output_path))
            except OSError as e:
                raise ConversionFailedError(
                    f"LibreOffice produced {produced} but couldn't move it to "
                    f"{output_path} (destination may be open elsewhere): {e}"
                ) from e

        return ConversionResult(output_path=output_path)
