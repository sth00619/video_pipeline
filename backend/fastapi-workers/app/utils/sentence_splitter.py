"""Lossless sentence splitting for narration, captions, and alignment."""

from __future__ import annotations

import re


# A period between digits is a decimal separator, never a sentence boundary.
_DECIMAL_RE = re.compile(r"(?<=\d)\.(?=\d)")
_ABBREVIATIONS = ("etc", "e.g", "i.e", "Inc", "Ltd", "Co", "vs", "St", "Dr", "Mr", "Ms", "No")
_PLACEHOLDER = "\u241f"
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?…])(?=[\"'\u201d\u2019)\]]*\s)")


def split_sentences(text: str) -> list[str]:
    """Split text without treating decimals or common abbreviations as endings.

    Returned strings keep their terminal punctuation. Whitespace surrounding a
    boundary is normalized away; all meaningful source characters are retained.
    """
    if not text or not text.strip():
        return []

    protected = _DECIMAL_RE.sub(_PLACEHOLDER, text)
    for abbreviation in _ABBREVIATIONS:
        protected = re.sub(
            rf"(?<![A-Za-z]){re.escape(abbreviation)}\.",
            abbreviation + _PLACEHOLDER,
            protected,
        )

    return [
        part.strip().replace(_PLACEHOLDER, ".")
        for part in _SENTENCE_BOUNDARY_RE.split(protected)
        if part.strip()
    ]
