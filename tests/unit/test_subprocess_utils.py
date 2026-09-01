"""Tests for the shared subprocess helper — uses sys.executable stand-ins
so no real external tool (soffice, pandoc) is needed."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from proteus.core.errors import ConversionFailedError, ConverterUnavailableError
from proteus.core.subprocess_utils import isolated_libreoffice_profile, run_subprocess


def test_run_subprocess_returns_completed_process_on_success():
    result = run_subprocess([sys.executable, "-c", "print('hi')"])
    assert result.returncode == 0
    assert "hi" in result.stdout


def test_run_subprocess_raises_conversion_failed_on_nonzero_exit():
    with pytest.raises(ConversionFailedError):
        run_subprocess([sys.executable, "-c", "import sys; sys.exit(3)"])


def test_run_subprocess_raises_conversion_failed_on_timeout():
    with pytest.raises(ConversionFailedError):
        run_subprocess(
            [sys.executable, "-c", "import time; time.sleep(5)"], timeout_s=0.1
        )


def test_run_subprocess_raises_converter_unavailable_on_missing_binary():
    with pytest.raises(ConverterUnavailableError):
        run_subprocess(["definitely-not-a-real-binary-xyz"])


def test_isolated_libreoffice_profile_yields_file_uri_arg_and_cleans_up():
    with isolated_libreoffice_profile() as arg:
        assert arg.startswith("-env:UserInstallation=file:")
        uri = arg.removeprefix("-env:UserInstallation=")
        profile_dir = Path(url2pathname(urlparse(uri).path))
        assert profile_dir.is_dir()

    assert not profile_dir.exists()
