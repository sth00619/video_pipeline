"""검증 사실의 수치·날짜를 잘라 쓰지 않도록 완전한 값 토큰으로 대조한다."""
from __future__ import annotations

import re
from typing import Any


_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_DATE = r"\d{4}[-./]\d{1,2}[-./]\d{1,2}"
_UNIT = rf"(?:조(?:\s*{_NUMBER}\s*억)?(?:\s*원)?|억원|만원|천원|억(?:\s*원)?|만(?:\s*원)?|원|%p|%|퍼센트포인트|퍼센트|bps?|bp|포인트|pt|배|달러|엔|유로|년|월|일|분기|단계|개|명)"
_VALUE_TOKEN = re.compile(
    rf"(?<![\d.,])(?:{_DATE}|(?:[₩$¥€]\s*)?{_NUMBER}(?:\s*{_UNIT})?)(?![A-Za-z\d.,])",
    re.IGNORECASE,
)
_UNIT_ALIASES = {
    "pt": ("pt", "포인트"),
    "포인트": ("pt", "포인트"),
}
_STRUCTURED_VALUE_SUFFIXES = (
    "%p", "%", "퍼센트포인트", "퍼센트", "bps", "bp", "포인트", "pt",
    "억원", "만원", "천원", "원", "배", "달러", "엔", "유로",
    "년", "월", "일", "분기", "단계", "개", "명",
)


def _normalise(value: Any) -> str:
    """공백류만 제거하고 부호·구두점·단위·대소문자는 보존한다."""
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _complete_value_tokens(text: Any) -> tuple[str, ...]:
    result: list[str] = []
    for match in _VALUE_TOKEN.finditer(str(text or "")):
        token = _normalise(match.group(0))
        if token and token not in result:
            result.append(token)
    return tuple(result)


def fact_value_evidence_tokens(fact: dict[str, Any]) -> tuple[str, ...]:
    """figure/fact에서 경계가 닫힌 수치·날짜 토큰을 원문 순서로 반환한다."""
    result: list[str] = []
    for key in ("figure", "fact"):
        for token in _complete_value_tokens(fact.get(key)):
            if token and token not in result:
                result.append(token)
    return tuple(result)


def text_contains_complete_value(
    text: Any,
    requested: Any,
    *,
    permit_structured_unit_suffix: bool = False,
) -> bool:
    """장면 문구가 요청값을 독립된 완전값으로 포함하는지 확인한다."""
    value = _normalise(requested)
    if not value or not any(char.isdigit() for char in value):
        return False
    allowed = {value}
    if permit_structured_unit_suffix:
        for suffix in _STRUCTURED_VALUE_SUFFIXES:
            if not value.endswith(suffix):
                allowed.add(f"{value}{suffix}")
    return bool(set(_complete_value_tokens(text)).intersection(allowed))


def verified_fact_contains_value(
    fact: dict[str, Any],
    requested: Any,
    *,
    require_structured_value_match: bool,
) -> bool:
    """요청값이 구조화 값 및 완전한 근거 토큰과 일치하는지 확인한다.

    `143조`를 `143조 5000억 원`의 일부로, `4배`를 `14배`의 일부로
    승인하지 않는다. 구조화 `value`가 있으면 오버레이 대표값과도 같아야 한다.
    `unit=pt`처럼 값과 단위가 분리된 기존 계약은 선언한 단위 별칭까지만 허용한다.
    """
    value = _normalise(requested)
    if not value or not any(char.isdigit() for char in value):
        return False

    structured = _normalise(fact.get("value"))
    if require_structured_value_match and structured and value != structured:
        return False

    allowed = {value}
    if require_structured_value_match and structured == value:
        # `value=2,650`, `figure=2,650포인트`처럼 구조화 값과 단위가
        # 분리된 기존 계약은 알려진 단일 단위가 정확히 뒤따를 때만 허용한다.
        for suffix in _STRUCTURED_VALUE_SUFFIXES:
            if not value.endswith(suffix):
                allowed.add(f"{value}{suffix}")
        unit = _normalise(fact.get("unit"))
        for alias in _UNIT_ALIASES.get(unit, (unit,) if unit else ()):
            if alias and not value.endswith(alias):
                allowed.add(f"{value}{alias}")

    tokens = set(fact_value_evidence_tokens(fact))
    return bool(tokens.intersection(allowed))
