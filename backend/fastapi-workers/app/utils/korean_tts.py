"""Korean speech-only text normalization for the TTS pipeline.

The visible script/subtitle must retain its original numeric form.  This
module is deliberately used only for text submitted to the TTS/STT alignment
pipeline so that a phrase such as ``6856의`` is spoken as ``육천 팔백 오십육의``
without changing what the viewer reads.
"""
from __future__ import annotations

import re


_DIGITS = ("영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
_SMALL_UNITS = ("", "십", "백", "천")
_LARGE_UNITS = ("", "만", "억", "조", "경")
_COUNTERS = "원|달러|엔|유로|주식|주|명|개|건|배|포인트|년|월|일|시|분|초|퍼센트"


def sino_korean_integer(raw: str) -> str:
    """Render an Arabic integer as a natural Sino-Korean cardinal reading."""
    digits = raw.replace(",", "")
    if not digits:
        return ""
    if not digits.isdigit():
        return raw
    if len(digits) > 1 and digits.startswith("0"):
        # Identifiers such as 010 must retain every leading zero when spoken.
        return " ".join(_DIGITS[int(char)] for char in digits)

    value = int(digits)
    if value == 0:
        return _DIGITS[0]

    groups: list[str] = []
    while value:
        groups.append(f"{value % 10_000:04d}")
        value //= 10_000

    parts: list[str] = []
    for group_index in range(len(groups) - 1, -1, -1):
        group = groups[group_index]
        words: list[str] = []
        for index, char in enumerate(group):
            digit = int(char)
            if digit == 0:
                continue
            power = 3 - index
            # 일십/일백/일천 is normally pronounced 십/백/천.
            digit_word = "" if digit == 1 and power else _DIGITS[digit]
            words.append(f"{digit_word}{_SMALL_UNITS[power]}")
        if words:
            chunk = " ".join(words)
            # 만 alone is conventionally read 일만, unlike 십/백/천.
            if group_index:
                chunk = f"{chunk} {_LARGE_UNITS[group_index]}"
            parts.append(chunk)

    return " ".join(parts)


def normalize_korean_numbers_for_tts(text: str) -> str:
    """Expand numeric values and common counters for Korean narration.

    Unlike ``\\b`` based replacement this intentionally matches digits next to
    Hangul suffixes (e.g. ``6856의``, ``783명``), because digits and Hangul are
    both word characters in Python regular expressions.
    """
    # Only remove thousands separators inside a number; prose punctuation stays intact.
    text = re.sub(r"(?<=\d),(?=\d)", "", text)

    def numeric_reading(whole: str, fraction: str | None = None) -> str:
        if fraction is None:
            return sino_korean_integer(whole)
        return f"{sino_korean_integer(whole)} 점 {' '.join(_DIGITS[int(char)] for char in fraction)}"

    def percent_replacement(match: re.Match[str]) -> str:
        return f"{numeric_reading(match.group(1), match.group(2))} 퍼센트"

    # Handle percent before decimal expansion so 6.56% does not leave a literal
    # percent sign after its digits have already become Hangul.
    text = re.sub(r"(?<![\d.])(\d+)(?:\.(\d+))?\s*%", percent_replacement, text)

    def decimal_replacement(match: re.Match[str]) -> str:
        return numeric_reading(match.group(1), match.group(2))

    text = re.sub(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])", decimal_replacement, text)

    def counter_replacement(match: re.Match[str]) -> str:
        return f"{sino_korean_integer(match.group(1))} "

    # Preserve the following counter and any Korean particle exactly as written.
    text = re.sub(rf"(?<!\d)(\d+)(?=({_COUNTERS}))", counter_replacement, text)

    return re.sub(r"(?<!\d)(\d+)(?!\d)", lambda match: sino_korean_integer(match.group(1)), text)
