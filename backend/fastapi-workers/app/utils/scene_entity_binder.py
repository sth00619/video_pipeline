"""씬별 개체·수치·근거 바인딩 유틸리티.

파이프라인 읽기 전용 모듈. narration_contract SHA-256 불변 원칙 준수.
LLM 호출 없음 — 결정론적 정규식 매칭과 사전 룩업만 사용.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Any


from app.utils.entity_english_map import FICTIONALIZED_LABEL_MAP

# 업종 키워드 → 가상 라벨 자동 폴백 (시드에 없는 기업명 처리)
_SECTOR_LABEL_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"반도체|하이닉스|마이크론|TSMC|파운드리"), "CHIP MAKER"),
    (re.compile(r"전기차|배터리|자동차|오토|모터"), "EV AUTOMAKER"),
    (re.compile(r"플래시|낸드|웨스턴|플래쉬"), "FLASH STORAGE CO"),
    (re.compile(r"AI|인공지능"), "AI TECH CORP"),
    (re.compile(r"은행|금융|증권|투자"), "FIN CORP"),
    (re.compile(r"바이오|제약|의약|헬스"), "BIO PHARMA CO"),
    (re.compile(r"통신|텔레콤|SKT|KT"), "TELECOM CORP"),
    (re.compile(r"철강|제철|포스코"), "STEEL CORP"),
    (re.compile(r"유통|쇼핑|마트|이커머스"), "RETAIL CORP"),
    (re.compile(r"게임|엔씨|넥슨|크래프톤"), "GAME CORP K"),
    (re.compile(r"항공|에어|진에어|제주항공"), "AIRLINE CORP K"),
    (re.compile(r"조선|해운|현대중|삼성중"), "SHIPBUILDING CORP K"),
]

# %p를 % 앞에 배치 (순서 중요: 더 구체적인 단위 먼저 매칭)
_FIGURE_RE = re.compile(
    r"[+-]?[\d,]+(?:\.\d+)?\s*"
    r"(?:%p|퍼센트포인트|포인트|pt|%|조|억|만|원|개월|년|선)"
)

# 수치 종류 분류 패턴
_KIND_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"%p|퍼센트포인트"), "pct_point"),
    (re.compile(r"%"), "rate"),
    (re.compile(r"조|억|만|원"), "amount"),
    (re.compile(r"개월|년"), "period"),
    (re.compile(r"선"), "index_level"),
    (re.compile(r"포인트|pt"), "points"),
]

# 방향 키워드 (부호 없는 수치에 방향 컨텍스트 부여)
_DIRECTION_UP = re.compile(r"상승|급등|올라|반등|강세|호조|증가|올랐|높아|상향")
_DIRECTION_DOWN = re.compile(r"하락|급락|떨어|빠졌|약세|감소|내려|낮아|하향|붕괴|폭락")

# 공백을 없앤 뒤 부분 문자열로 비교하면 '기업은', '지금'이 은/금으로 바뀐다.
# 형태소 분석기 의존성을 추가하지 않고, 독립 어절과 명시적인 조사만 허용한다.
# 의미가 모호한 합성어를 추측하지 않는 보수적인 계약이며 대본은 수정하지 않는다.
_ENTITY_PARTICLES = (
    "으로부터", "에서부터", "에게서는", "에서는", "에서도", "으로는", "으로도",
    "에게서", "한테서", "이랑", "이라면", "이라고", "이라는", "이란",
    "로부터", "에게", "한테", "에서", "까지", "부터", "처럼", "보다",
    "마다", "조차", "마저", "이라", "으로", "로는", "로도", "에도",
    "에는", "에만", "와는", "과는", "라고", "라는", "란", "랑",
    "입니다", "이었다", "였다", "이다", "이고", "이며", "인",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로",
)
_COMMODITY_COMPOUNDS = {
    "금": ("금값", "금가격", "금시세", "금선물", "금현물"),
    "은": ("은값", "은가격", "은시세", "은선물", "은현물"),
}


@lru_cache(maxsize=2048)
def _entity_pattern(entity: str) -> re.Pattern:
    """회사명 내부 띄어쓰기는 허용하되 어절 경계·조사는 보존한다."""
    canonical = unicodedata.normalize("NFKC", entity).strip().casefold()
    aliases = (canonical, *_COMMODITY_COMPOUNDS.get(canonical, ()))
    names = [r"\s*".join(re.escape(ch) for ch in name if not ch.isspace()) for name in aliases]
    particles = "|".join(re.escape(p) for p in sorted(_ENTITY_PARTICLES, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + "|".join(names) + r")(?:(?:" + particles + r"))?(?!\w)")


def entity_is_mentioned(text: str, entity: str) -> bool:
    """조사·부분 음절을 엔티티로 오인하지 않는 공통 대조 함수."""
    if not str(entity).strip():
        return False
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return bool(_entity_pattern(str(entity)).search(normalized))


@dataclass
class SceneEntityBinding:
    scene_id: str
    scene_index: int
    narration: str                        # 원문 그대로 (해시 검증용)
    narration_hash: str                   # SHA-256 (파이프라인 불변성 보장)
    core_entities: list[str]              # 대본에서 언급된 구체 금융 명사
    core_figures: list[dict]              # {"raw": "0.5%p", "kind": "pct_point", "direction": "up|down|neutral"}
    has_news_evidence: bool               # keyword_news와 교차 확인
    suggested_visual_type: str            # 초기 visual_type 제안값
    fictionalized_labels: dict[str, str]  # 실명 → 가상 라벨 룩업


def _fictionalize(entity: str) -> str:
    """맵에 없는 기업명은 업종 규칙으로 자동 일반화. 매칭 안 되면 앞 2글자 + CORP."""
    if entity in FICTIONALIZED_LABEL_MAP:
        return FICTIONALIZED_LABEL_MAP[entity]
    for pattern, label in _SECTOR_LABEL_RULES:
        if pattern.search(entity):
            return label
    # 마지막 폴백: 앞 2글자 + CORP (최소한 실명 그대로보단 안전)
    safe_prefix = re.sub(r"\W", "", entity)[:4].upper()
    return f"{safe_prefix} CORP" if safe_prefix else "UNKNOWN CORP"


def _classify_figure_kind(raw: str) -> str:
    for pattern, kind in _KIND_MAP:
        if pattern.search(raw):
            return kind
    return "amount"


def _figure_direction(raw: str, narration_context: str) -> str:
    """수치의 문맥 방향을 추정. 부호가 있으면 부호 우선, 없으면 주변 문맥."""
    stripped = raw.strip()
    if stripped.startswith("+"):
        return "up"
    if stripped.startswith("-"):
        return "down"
    # 부호 없는 경우: 나레이션 전체 문맥에서 방향 키워드 탐색
    if _DIRECTION_UP.search(narration_context):
        return "up"
    if _DIRECTION_DOWN.search(narration_context):
        return "down"
    return "neutral"


def _extract_figures(narration: str) -> list[dict]:
    results = []
    for match in _FIGURE_RE.finditer(narration):
        raw = match.group(0).strip()
        kind = _classify_figure_kind(raw)
        direction = _figure_direction(raw, narration)
        results.append({"raw": raw, "kind": kind, "direction": direction})
    return results


def _extract_entities(narration: str, verified_facts: list[dict]) -> list[str]:
    """대본에서 verified_facts의 핵심 명사가 언급된 것을 추출.

    verified_facts 내 keyword, entity, company 등의 필드를 탐색하고
    narration에 등장하는 것만 반환한다. LLM 호출 없음.
    """
    candidates: set[str] = set()
    for fact in verified_facts:
        for key in ("keyword", "entity", "company", "ticker", "subject"):
            value = fact.get(key)
            if isinstance(value, str) and len(value) >= 2:
                candidates.add(value.strip())
        # keywords 리스트 형태
        for item in fact.get("keywords", []) or []:
            if isinstance(item, str) and len(item) >= 2:
                candidates.add(item.strip())

    # 나레이션에 실제 등장하는 것만 필터
    found = []
    for candidate in sorted(candidates):
        if entity_is_mentioned(narration, candidate):
            found.append(candidate)

    # FICTIONALIZED_LABEL_MAP 키도 추가 탐색
    for entity in FICTIONALIZED_LABEL_MAP:
        if entity_is_mentioned(narration, entity) and entity not in found:
            found.append(entity)

    return found


def bind_scene_entities(
    sections: list[dict],
    verified_facts: list[dict],
    keyword_news: list[dict],
) -> list[SceneEntityBinding]:
    """씬별 엔티티·수치·뉴스 근거를 바인딩한다.

    - LLM 호출 없음, 결정론적 정규식 매칭만 사용
    - narration 텍스트는 읽기만 하고, 절대 수정하지 않는다
    - SHA-256 해시를 기록해 downstream 파이프라인이 불변성을 검증할 수 있게 함
    """
    # keyword_news 검색용 텍스트 풀 (title + summary)
    news_corpus = " ".join(
        f"{item.get('title', '')} {item.get('summary', '')}"
        for item in (keyword_news or [])
    ).lower()

    results: list[SceneEntityBinding] = []
    for idx, section in enumerate(sections or []):
        narration = str(section.get("content") or section.get("text") or "").strip()
        scene_id = str(section.get("scene_id") or section.get("id") or idx)
        h = hashlib.sha256(narration.encode("utf-8")).hexdigest()

        core_entities = _extract_entities(narration, verified_facts)
        core_figures = _extract_figures(narration)

        # 뉴스 근거 교차 확인
        has_news = bool(
            core_entities and any(
                entity_is_mentioned(news_corpus, entity)
                for entity in core_entities
            )
        )

        # 가상 라벨 룩업 (엔티티별 자동 생성)
        fictionalized = {entity: _fictionalize(entity) for entity in core_entities}

        # visual_type 제안 (뉴스 근거 있으면 article_evidence 우선 제안)
        suggested = "article_evidence" if has_news and core_entities else "semantic_illustration"

        results.append(SceneEntityBinding(
            scene_id=scene_id,
            scene_index=idx,
            narration=narration,
            narration_hash=h,
            core_entities=core_entities,
            core_figures=core_figures,
            has_news_evidence=has_news,
            suggested_visual_type=suggested,
            fictionalized_labels=fictionalized,
        ))

    return results


def compute_grounding_score(prompt_text: str, core_entities: list[str]) -> float:
    """이미지 생성 전 프롬프트에 core_entities 관련 표현이 얼마나 포함됐는지 계산.

    실명 대신 fictionalized_label 기준으로도 검색한다.
    quality/images.json 에 'grounding_score_pre' 필드로 기록할 것.
    """
    if not core_entities or not prompt_text:
        return 1.0
    text_lower = prompt_text.lower()
    matched = sum(
        1 for entity in core_entities
        if entity_is_mentioned(text_lower, entity)
        or entity_is_mentioned(text_lower, _fictionalize(entity))
    )
    return round(matched / len(core_entities), 3)
