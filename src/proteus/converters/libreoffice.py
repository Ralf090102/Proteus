"""LibreOffice-headless-backed converters: docx -> pdf, pptx -> pdf,
ppt -> pdf.

Shells out to `soffice --headless --convert-to pdf --outdir <dir> <input>`
inside a fresh, isolated user profile per call (see
core/subprocess_utils.isolated_libreoffice_profile) to avoid profile-lock
contention if multiple calls happen back to back.

convert()/is_available()/tool_checks() have no format-specific logic
beyond the "--convert-to pdf" target — the same soffice invocation
handles docx, pptx, and legacy binary ppt sources identically (confirmed
against real LibreOffice for all three). PptxToPdfConverter/
PptToPdfConverter subclass LibreOfficeConverter purely to override
from_ext/to_ext, same pattern as converters/image.py's per-pair Pillow
subclasses — those two attributes are used in exactly one place
(convert()'s "not found" error message), but leaving them at their
inherited docx/pdf default would make that message say "Install it to
convert docx->pdf" for a pptx/ppt conversion, which is wrong.
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

        # LibreOffice always writes its output directly into --outdir,
        # unconditionally overwriting anything already there under
        # whatever name it derives — pointing --outdir at an isolated
        # temp dir (rather than output_path.parent, the real destination)
        # means that can never collide with and silently clobber an
        # unrelated file that happens to share the input's stem. The only
        # write into the real destination is the final move below, and
        # only at the exact path the caller asked for.
        try:
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

                # Find what soffice actually produced rather than
                # predicting its filename ourselves: --outdir is an
                # isolated temp dir nothing else writes into, so whatever
                # single PDF lands there is the real output, regardless of
                # what soffice named it. Predicting `<input-stem>.pdf`
                # would depend on Proteus's Path.stem computation matching
                # soffice's own filename derivation exactly for every
                # possible unicode/space content in the input name — an
                # untested assumption this sidesteps entirely.
                produced_candidates = sorted(Path(tmp_outdir).glob("*.pdf"))
                if not produced_candidates:
                    raise ConversionFailedError(
                        f"LibreOffice reported success but produced no PDF in {tmp_outdir}"
                    )
                if len(produced_candidates) > 1:
                    raise ConversionFailedError(
                        f"LibreOffice reported success but produced "
                        f"{len(produced_candidates)} PDF files in {tmp_outdir}, "
                        f"expected exactly 1"
                    )
                produced = produced_candidates[0]
                ensure_output_created(produced, "LibreOffice")

                try:
                    # shutil.move(), not Path.replace()/os.replace(): the
                    # temp staging dir and the real destination can be on
                    # different drives (the common case for this repo —
                    # %TEMP% is on C:, the project is on D:), and
                    # os.replace()'s MoveFileExW call has no
                    # MOVEFILE_COPY_ALLOWED fallback for that — it fails
                    # outright with WinError 17 cross-drive. shutil.move()
                    # falls back to copy+delete automatically.
                    shutil.move(str(produced), str(output_path))
                except OSError as e:
                    raise ConversionFailedError(
                        f"LibreOffice produced {produced} but couldn't move it to "
                        f"{output_path} (destination may be open elsewhere): {e}"
                    ) from e
        except OSError as e:
            # Only reachable for a failure setting up the temp staging
            # dir itself (e.g. disk full) — the move failure above already
            # converts its own OSErrors to ConversionFailedError before
            # they'd reach here.
            raise ConversionFailedError(
                f"Could not set up a temporary working directory for LibreOffice: {e}"
            ) from e

        return ConversionResult(output_path=output_path)


class PptxToPdfConverter(LibreOfficeConverter):
    from_ext = "pptx"
    to_ext = "pdf"


class PptToPdfConverter(LibreOfficeConverter):
    from_ext = "ppt"
    to_ext = "pdf"
