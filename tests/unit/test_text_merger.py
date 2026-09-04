"""Unit tests for MarkdownMerger/TextMerger — plain concatenation, no
external tool or optional extra involved, so these run directly (no
mock/double needed, same tier as PdfMerger's tests)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteus.converters.merge import MarkdownMerger, TextMerger
from proteus.core.errors import ConversionFailedError

FIXTURES = Path(__file__).parent.parent / "fixtures"
SAMPLE_MD = FIXTURES / "sample.md"
SAMPLE2_MD = FIXTURES / "sample2.md"
SAMPLE_TXT = FIXTURES / "sample.txt"
SAMPLE2_TXT = FIXTURES / "sample2.txt"


def test_markdown_merger_is_available_always_true():
    assert MarkdownMerger().is_available() is True


def test_text_merger_is_available_always_true():
    assert TextMerger().is_available() is True


def test_markdown_merger_combines_both_files_content(tmp_path):
    output_path = tmp_path / "merged.md"
    result = MarkdownMerger().merge([SAMPLE_MD, SAMPLE2_MD], output_path)

    assert result.output_path == output_path
    combined = output_path.read_text(encoding="utf-8")
    assert "Proteus Sample Document" in combined
    assert "Second Sample Document" in combined
    # Order preserved as given (caller is responsible for sorting) — the
    # first file's content appears before the second's, not interleaved.
    assert combined.index("Proteus Sample Document") < combined.index(
        "Second Sample Document"
    )


def test_text_merger_combines_both_files_content(tmp_path):
    output_path = tmp_path / "merged.txt"
    result = TextMerger().merge([SAMPLE_TXT, SAMPLE2_TXT], output_path)

    assert result.output_path == output_path
    combined = output_path.read_text(encoding="utf-8")
    assert "First sample text fixture" in combined
    assert "Second sample text fixture" in combined


def test_merge_raises_conversion_failed_for_unreadable_file(tmp_path):
    missing = tmp_path / "does-not-exist.txt"

    with pytest.raises(ConversionFailedError):
        TextMerger().merge([SAMPLE_TXT, missing], tmp_path / "out.txt")


def test_merge_does_not_destroy_pre_existing_output_on_failure(tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    output_path = tmp_path / "out.txt"
    output_path.write_text("important pre-existing content")

    with pytest.raises(ConversionFailedError):
        TextMerger().merge([SAMPLE_TXT, missing], output_path)

    assert output_path.read_text() == "important pre-existing content"
    assert list(tmp_path.glob(".proteus-tmp-*")) == []
