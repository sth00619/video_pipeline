"""Retry decisions for paid image generation calls.

Only provider/network faults are safe to retry.  Local Python, configuration,
and output-validation errors are deterministic for a given scene and must stop
before they fan out across every worker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    reason: str


_LOCAL_ERRORS = (TypeError, KeyError, AttributeError, NameError, SyntaxError, ImportError, ValueError)
_TRANSIENT_TEXT = re.compile(
    r"\b(?:429|500|501|502|503|504|505|506|507|508|509|rate[ -]?limit|"
    r"too many requests|temporar(?:y|ily)|unavailable|timeout|timed out|"
    r"connection reset|connection aborted|connection refused|network)\b",
    re.IGNORECASE,
)


def classify_image_error(exc: BaseException) -> RetryDecision:
    """Return the conservative retry classification used by image workers."""
    if isinstance(exc, _LOCAL_ERRORS):
        return RetryDecision(False, f"local {type(exc).__name__}")
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return RetryDecision(True, type(exc).__name__)

    message = str(exc or "")
    if _TRANSIENT_TEXT.search(message):
        return RetryDecision(True, "transient provider/network response")
    return RetryDecision(False, f"unclassified {type(exc).__name__}")


def error_signature(exc: BaseException) -> str:
    """Stable enough to detect the same outage/configuration fault across scenes."""
    text = re.sub(r"\d+", "#", str(exc or "").strip().lower())
    return f"{type(exc).__name__}:{text[:180]}"
