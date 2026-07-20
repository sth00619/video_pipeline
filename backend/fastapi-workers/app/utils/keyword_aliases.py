"""Shared seed/candidate normalisation. Java reads the same JSON source."""
from __future__ import annotations

import json
import re
from pathlib import Path

def _load() -> dict:
    for path in (Path('/app/shared/keyword_aliases.json'), Path(__file__).resolve().parents[3] / 'shared' / 'keyword_aliases.json'):
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
    raise RuntimeError('shared keyword_aliases.json is missing')

RULES = _load()
ALIASES = {re.sub(r'\s+', '', k).casefold(): v for k, v in RULES['aliases'].items()}
STOP_WORDS = set(RULES['stop_words'])

def normalise_terms(text: str) -> set[str]:
    compact = re.sub(r'\s+', '', text or '').casefold()
    terms: set[str] = set()
    for alias, canonical in ALIASES.items():
        if alias in compact:
            terms.update(canonical)
    for quarter in re.findall(r'([1-4])\s*(?:분기|[Qq])', text or ''):
        terms.add(f'Q{quarter}')
    for token in re.findall(r'[A-Za-z가-힣]{2,}|\d{4}', text or ''):
        if token not in STOP_WORDS and not token.isdigit():
            terms.add(token)
    return terms

def seed_overlap(seed: str, candidate_text: str) -> list[str]:
    return sorted(normalise_terms(seed) & normalise_terms(candidate_text))

def seed_match(seed: str, candidate_text: str) -> bool:
    wanted = normalise_terms(seed)
    return not wanted or len(seed_overlap(seed, candidate_text)) >= (1 if len(wanted) == 1 else 2)
