"""Shared topic-evidence rules used before keyword confirmation and scripting."""

from __future__ import annotations

import re
from typing import Iterable


# Unicode escapes keep these policy tokens stable even when this repository is
# opened in a Windows shell with a legacy code page.
_BROAD_MARKET_TOKENS = {
    "market", "markets", "stock", "stocks", "equity", "equities", "outlook", "us", "u.s.", "usa",
    "forecast", "index", "indices", "economy", "economic", "macro", "marketplace",
    "\ubbf8\uad6d", "\ud55c\uad6d", "\uad6d\ub0b4", "\uae00\ub85c\ubc8c", "\uc99d\uc2dc", "\uc8fc\uc2dd", "\uc2dc\uc7a5",
    "\uc804\ub9dd", "\ud558\ubc18\uae30", "\uc0c1\ubc18\uae30", "\uacbd\uc81c", "\uac70\uc2dc", "\ucf54\uc2a4\ud53c", "\ucf54\uc2a4\ub2e5",
    "\ub098\uc2a4\ub2e5", "\uc9c0\uc218", "\uae08\ub9ac",
}

_SEED_STOP_WORDS = {
    "\ucf54\uc2a4\ud53c", "\ucf54\uc2a4\ub2e5", "\uc8fc\uc2dd", "\uc99d\uc2dc", "\uc2dc\uc7a5", "\uacbd\uc81c", "\ub274\uc2a4", "\uad00\ub828", "\ubd84\uc11d",
    "\ubc29\ud5a5", "\uc8fc\uac00", "\uc624\ub298", "\ucd5c\uadfc",
}


def specific_terms(seed: str) -> list[str]:
    """Return non-generic terms that make an editorial brief distinguishable."""
    terms: list[str] = []
    for raw in re.split(r"\s+", seed or ""):
        token = re.sub(r"[^0-9A-Za-z\uac00-\ud7a3]", "", raw).strip()
        if not token or token.isdigit() or token.lower() in _SEED_STOP_WORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def is_market_level_forecast(terms: Iterable[str]) -> bool:
    """True only for broad market outlooks that can rely on a market snapshot.

    Named companies, sectors, or policy events must still have direct news evidence.
    """
    tokens = [
        token.lower()
        for phrase in terms
        for token in re.split(r"\s+", phrase or "")
        if token
    ]
    return bool(tokens) and all(token in _BROAD_MARKET_TOKENS for token in tokens)
