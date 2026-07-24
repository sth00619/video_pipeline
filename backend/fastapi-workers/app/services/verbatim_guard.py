"""Deterministic evidence checks for every numeric string shown on screen."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_NUMBER_TOKEN = re.compile(
    # Korean particles legitimately follow a complete token (``12.5%의``),
    # so only another digit/Latin letter/decimal point may extend a token.
    r"(?<![0-9A-Za-z.])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(?:%|퍼센트|bp|bps|포인트|원|달러|억|만|조|개|명|년|월|일|배|위|분|초))?(?![0-9A-Za-z.])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    matched_sources: list[str] = field(default_factory=list)
    numeric_tokens: list[str] = field(default_factory=list)


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _walk_strings(value: Any, label: str) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        output: list[tuple[str, str]] = []
        for key, item in value.items():
            output.extend(_walk_strings(item, f"{label}.{key}"))
        return output
    if isinstance(value, list):
        output: list[tuple[str, str]] = []
        for index, item in enumerate(value):
            output.extend(_walk_strings(item, f"{label}[{index}]"))
        return output
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return [(label, _normalise(value))]
    return []


def _sources(evidence: Any) -> list[tuple[str, str]]:
    if not isinstance(evidence, dict):
        return []
    result: list[tuple[str, str]] = []
    article = evidence.get("article_capture")
    if isinstance(article, dict) and article.get("quote"):
        result.append(("article_capture.quote", _normalise(article["quote"])))
    for index, item in enumerate(evidence.get("verified_facts") or []):
        if isinstance(item, dict):
            for field in ("figure", "fact"):
                if item.get(field) is not None:
                    result.append((f"verified_facts[{index}].{field}", _normalise(item[field])))
    result.extend(_walk_strings(evidence.get("market_snapshot") or {}, "market_snapshot"))
    return [(label, text) for label, text in result if text]


def _contains_token(source: str, token: str) -> bool:
    return bool(re.search(rf"(?<![0-9A-Za-z.]){re.escape(token)}(?![0-9A-Za-z.])", source))


def validate(text: str, evidence: dict | None) -> ValidationResult:
    """Allow creative non-numeric text; require every shown number to be grounded.

    Whitespace is normalised, but decimal separators, units and percent symbols
    are deliberately *not* converted.  A spoken narration can say 퍼센트 while
    a visual layer keeps `%`; the two channels are validated independently.
    """
    displayed = _normalise(text)
    if not displayed:
        return ValidationResult(True)
    tokens = [match.group(0).replace(" ", "") for match in _NUMBER_TOKEN.finditer(displayed)]
    if not tokens:
        return ValidationResult(True)
    candidates = _sources(evidence or {})
    if not candidates:
        return ValidationResult(False, ["numeric_screen_text_without_evidence"], numeric_tokens=tokens)

    matched: list[str] = []
    missing: list[str] = []
    for token in tokens:
        source_hits = [label for label, source in candidates if _contains_token(source.replace(" ", ""), token)]
        if source_hits:
            matched.extend(source_hits)
        else:
            missing.append(token)
    if missing:
        return ValidationResult(
            False,
            [f"ungrounded_numeric_token:{token}" for token in missing],
            sorted(set(matched)),
            tokens,
        )
    return ValidationResult(True, matched_sources=sorted(set(matched)), numeric_tokens=tokens)
