"""Deterministic time interpretation for earnings/topic keywords."""
from __future__ import annotations

import re
from datetime import date


def resolve_keyword_time_context(keyword: str, today: date | None = None) -> dict:
    today = today or date.today()
    match = re.search(r"(?:([12]0\d{2})\s*년?\s*)?([1-4])\s*(?:분기|[Qq])", keyword or "")
    if not match:
        return {"detected": False, "requires_evidence": False, "message": "시간 조건 없음"}
    explicit_year, quarter_text = match.groups()
    quarter = int(quarter_text)
    current_quarter = ((today.month - 1) // 3) + 1
    year = int(explicit_year) if explicit_year else (today.year if quarter < current_quarter else today.year - 1)
    requires_evidence = year > today.year or (year == today.year and quarter >= current_quarter)
    if requires_evidence:
        message = f"{year}년 {quarter}분기 실적은 아직 발표 근거를 확인할 수 없습니다. 연도·분기 또는 근거 자료를 확인해 주세요."
    else:
        message = f"'{quarter}분기'는 가장 최근에 확인 가능한 {year}년 {quarter}분기 기준으로 해석했습니다."
    return {"detected": True, "year": year, "quarter": quarter,
            "requires_evidence": requires_evidence, "message": message}
