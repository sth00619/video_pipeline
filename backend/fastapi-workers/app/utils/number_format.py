"""Shared display formatting for verified financial values.

Visible overlays keep Arabic numerals while TTS expands the same numeric source
through :mod:`app.utils.korean_tts`.  Keeping both modules adjacent prevents
the display and spoken pipelines from inventing separate units or rounding.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.utils.korean_tts import sino_korean_integer


VerifiedNumberFormat = Literal[
    "numeral_grouped", "korean_compact", "percent", "point", "date_ym",
]


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not a verified numeric value")
    try:
        return Decimal(str(value))
    except Exception as exc:  # Decimal has several implementation exceptions.
        raise ValueError(f"invalid verified numeric value: {value!r}") from exc


def _signed(value: Decimal, rendered: str, sign: bool) -> str:
    if sign and value > 0:
        return "+" + rendered
    return rendered


def _compact_won(value: Decimal) -> str:
    """Return a stable Korean currency display without changing TTS reading.

    This uses the same 만/억/조 grouping as ``sino_korean_integer``.  The
    import above deliberately keeps the spoken and display modules coupled;
    display output itself stays compact and numeral-led for a screen overlay.
    """
    integer = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    _ = sino_korean_integer(str(abs(integer)))  # validate the shared grouping input
    sign = "-" if integer < 0 else ""
    integer = abs(integer)
    if integer < 10_000:
        if integer >= 1_000 and integer % 1_000 == 0:
            return f"{sign}{integer // 1_000}천 원"
        return f"{sign}{integer:,}원"
    chunks: list[str] = []
    for divisor, label in ((10**12, "조"), (10**8, "억"), (10**4, "만")):
        amount, integer = divmod(integer, divisor)
        if amount:
            chunks.append(f"{amount:,}{label}")
    if integer:
        if integer >= 1_000 and integer % 1_000 == 0:
            chunks.append(f"{integer // 1_000}천")
        else:
            chunks.append(f"{integer:,}")
    return f"{sign}{' '.join(chunks)} 원"


def format_verified_value(
    value: object,
    format: VerifiedNumberFormat,
    *,
    sign: bool = False,
) -> str:
    """Format a previously verified value for visible Korean overlays.

    Percent inputs are decimal ratios (``0.021`` -> ``+2.1%``); point inputs
    are absolute point changes (``12.4`` -> ``+12.4pt``).  The formats are
    intentionally non-convertible so a point value cannot be mislabeled as a
    percentage, or vice versa.
    """
    if format == "date_ym":
        if isinstance(value, datetime):
            return value.strftime("%Y.%m")
        if isinstance(value, date):
            return value.strftime("%Y.%m")
        raw = str(value).strip()
        if len(raw) >= 7 and raw[:4].isdigit() and raw[4] in "-./" and raw[5:7].isdigit():
            return f"{raw[:4]}.{raw[5:7]}"
        raise ValueError("date_ym requires ISO-like verified date")

    numeric = _decimal(value)
    if format == "numeral_grouped":
        if numeric != numeric.to_integral_value():
            raise ValueError("numeral_grouped requires an integer")
        return _signed(numeric, f"{int(numeric):,}", sign)
    if format == "korean_compact":
        return _compact_won(numeric)
    if format == "percent":
        rendered = (numeric * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return _signed(numeric, f"{rendered}%", sign)
    if format == "point":
        rendered = numeric.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return _signed(numeric, f"{rendered}pt", sign)
    raise ValueError(f"unsupported verified number format: {format}")


def indexed_basis(reference: object, baseline: object = 100) -> str:
    """Format the mandatory basis label for a normalized/indexed series."""
    label = str(reference or "").strip()
    numeric = _decimal(baseline)
    if not label:
        raise ValueError("indexed series requires a comparison basis label")
    if numeric <= 0:
        raise ValueError("indexed baseline must be positive")
    rendered = numeric.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    rendered_text = str(int(rendered)) if rendered == rendered.to_integral_value() else f"{rendered:.1f}"
    return f"{label} = {rendered_text}"
