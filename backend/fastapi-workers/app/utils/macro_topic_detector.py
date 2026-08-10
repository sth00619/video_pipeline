"""매크로/글로벌 경제 주제 감지 유틸.

카테고리 자동 추론의 단일 판정 로직. KOSPI/KOSDAQ/INDIVIDUAL_STOCK/
ASSOCIATED_STOCKS 카테고리는 market_data_collector.collect_for_category()에서
미국 지표(us.*)를 전혀 수집하지 않는다. 사용자가 "연준 금리", "FOMC" 같은
매크로 주제를 이 카테고리로 넣으면 팩트체크에 필요한 근거 데이터 자체가
없는 상태로 스크립트 생성이 진행되어 게이트 타임아웃/품질 저하로 이어진다.

이 모듈은 강제 변경이 아니라 "제안"만 한다. 최종 카테고리 결정은 항상
사용자(UI) 또는 명시적 API 요청값이 우선한다.
"""
from __future__ import annotations

import re

# 이 키워드가 제목/시드에 하나라도 포함되면 GLOBAL_MACRO를 제안한다.
# 유지보수: 새 매크로 이벤트/지표가 생기면 여기에만 추가하면 된다.
MACRO_SIGNAL_TERMS = [
    "연준", "FOMC", "fomc", "금리인하", "금리인상", "기준금리",
    "환율", "달러인덱스", "DXY", "국채", "국채금리", "10년물",
    "CPI", "PCE", "물가지수", "소비자물가", "고용지표", "실업률",
    "비농업고용", "PMI", "GDP", "양적긴축", "양적완화", "테이퍼링",
    "파월", "옐런", "잭슨홀",
]

# 이미 이 카테고리라면 굳이 매크로로 전환 제안을 하지 않는다.
# (사용자가 이미 매크로 계열을 선택한 상태)
_SKIP_CATEGORIES = {"GLOBAL_MACRO", "CUSTOM", "CRYPTO"}


def detect_macro_signal(title: str) -> list[str]:
    """제목/시드 텍스트에서 매크로 신호 키워드를 찾아 반환한다.

    반환값이 비어 있지 않으면 GLOBAL_MACRO 카테고리 전환을 제안할 수 있다.
    """
    if not title:
        return []
    compact = title.strip()
    found = [term for term in MACRO_SIGNAL_TERMS if term.casefold() in compact.casefold()]
    return found


def should_suggest_global_macro(title: str, current_category: str | None) -> bool:
    """현재 카테고리가 매크로 지표를 수집하지 않는 카테고리이고,
    제목에 매크로 신호가 있으면 True."""
    if (current_category or "").upper() in _SKIP_CATEGORIES:
        return False
    return len(detect_macro_signal(title)) > 0
