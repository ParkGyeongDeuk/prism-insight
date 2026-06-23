"""
Report text loading helpers for LLM-facing consumers.

Markdown reports are the canonical analysis artifact. PDF extraction remains as
backward-compatible fallback for older callers that still pass generated PDFs.
"""

from __future__ import annotations

import re
from pathlib import Path


_BASE64_HTML_IMG_RE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*(['\"])data:image/[^;'\"]+;base64,[^'\"]+\1[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_BASE64_MD_IMG_RE = re.compile(
    r"!\[[^\]]*\]\(\s*data:image/[^;)]+;base64,[^)]+\)",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_report_markdown(markdown_text: str) -> str:
    """Remove embedded base64 images while preserving report text and tables."""
    without_html_images = _BASE64_HTML_IMG_RE.sub("\n\n", markdown_text)
    without_md_images = _BASE64_MD_IMG_RE.sub("\n\n", without_html_images)
    return without_md_images


def read_report_text_for_llm(report_path: str | Path) -> str:
    """Read a report as LLM input text.

    Markdown is read directly and sanitized. PDF paths use the legacy extraction
    path so existing manual callers keep working.
    """
    path = Path(report_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from pdf_converter import pdf_to_markdown_text

        return pdf_to_markdown_text(path)

    text = path.read_text(encoding="utf-8")
    if suffix in {".md", ".markdown"}:
        return sanitize_report_markdown(text)
    return text
