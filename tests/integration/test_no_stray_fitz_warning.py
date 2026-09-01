"""Regression test for a real reported bug: a plain docx->pdf conversion
used to print a scary, unrelated "fitz API is deprecated" warning (from
pdf2docx/pymupdf, eagerly imported by core/registry.py regardless of which
pair was actually being converted) that made a working conversion look
broken. See converters/pdf_extract.py's module docstring for the fix.

Needs a genuinely fresh subprocess, not just an in-process check — Python
caches modules in sys.modules per-process, so anything already imported
by an earlier test in the same pytest run would hide a regression here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SAMPLE_DOCX = Path(__file__).parent.parent / "fixtures" / "sample.docx"


@pytest.mark.integration
def test_docx_to_pdf_in_a_fresh_process_never_mentions_fitz(tmp_path):
    output_path = tmp_path / "sample.pdf"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "proteus.cli",
            "convert",
            str(SAMPLE_DOCX),
            "--to",
            "pdf",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined_output = result.stdout + result.stderr
    assert "fitz" not in combined_output.lower(), combined_output
    assert result.returncode == 0, combined_output
    assert output_path.exists()
