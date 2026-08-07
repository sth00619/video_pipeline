"""대본이 실제로 말하는 검증 수치만 V5 primary 표면 좌표 계획으로 변환한다.

이 모듈은 이미지를 그리지 않고 값을 만들지도 않는다. ``script_worker``가
채운 ``verified_facts`` 원문과 이 장면의 내러티브(``content``/``text``/
``title``, 즉 TTS가 실제로 읽는 문장)를 대조해, 이 장면이 실제로 말하는
수치 하나만 골라 소품 표면 좌표(anchor)를 붙인다.

같은 ``verified_facts`` 리스트가 모든 장면에 동일하게 붙어 있으므로, 이
내러티브 대조가 없으면 다른 장면의 수치가 엉뚱한 소품에 걸릴 수 있다.
값 자체는 절대 가공하지 않고 ``fact["figure"]`` 원문 그대로 넘기며, 최종
합성 직전 ``diegetic_fact_overlay.facts_from_verified_scene``이 같은 원문과
다시 한번 문자열 대조 검증한다(fail-closed, 이중 검증).

호출자는 아키타입을 이 모듈이 다시 추천하게 두지 않고, 실제 이미지
프롬프트를 만든 계약(``runtime_contract.attach_v5_scene_contracts``)이
확정한 archetype을 그대로 넘겨야 한다. 그래야 오버레이 좌표가 실제로
그려질 무대와 항상 일치한다.
"""
from __future__ import annotations

import re
from typing import Any

from app.v5.scene.scene_type_archetypes import primary_surface_region


# 채널 레퍼런스 관찰(경제사냥꾼): 수치가 놓이는 소품의 질감에 맞춰 글자
# 색상 계열만 고른다(밝은 배경엔 어두운 글자, 어두운 화면엔 밝은 글자).
# 배경 카드를 새로 그리지 않으므로 이 선택은 색상 팔레트에만 영향을 준다.
_OVERLAY_SURFACE_KIND_BY_ARCHETYPE: dict[str, str] = {
    "port_emergency": "placard",
    "retail_shock": "monitor",
    "classroom": "gauge_caption",
    "weather_map": "monitor",
    "risk_control_room": "monitor",
    "trade_calculator": "placard",
    "data_lab": "monitor",
    "briefing_podium": "placard",
    "real_estate_office": "placard",
    "job_market_hall": "monitor",
}

_TRAILING_PARTICLES = re.compile(r"[의은는이가을를에]+$")


def _normalise_for_match(value: str) -> str:
    return "".join(str(value).split()).casefold()


def _label_from_fact_text(fact_text: str, max_len: int = 14) -> str:
    """검증 문장에서 숫자 이전 구절만 짧은 표면 라벨로 쓴다."""
    stripped = str(fact_text or "").strip()
    digit_match = re.search(r"\d", stripped)
    head = stripped[: digit_match.start()] if digit_match else stripped
    head = _TRAILING_PARTICLES.sub("", head.strip())
    head = head.strip(" ,.:-")
    return head[:max_len] or "확인 수치"


def _select_verified_fact(scene: dict[str, Any]) -> tuple[int, str, str] | None:
    """이 장면 내러티브에 실제로 등장하는 검증 사실 하나만 고른다."""
    verified_facts = scene.get("verified_facts")
    if not isinstance(verified_facts, list) or not verified_facts:
        return None
    narration = " ".join(str(scene.get(key) or "") for key in ("content", "text", "title"))
    normalised_narration = _normalise_for_match(narration)
    if not normalised_narration:
        return None
    for index, fact in enumerate(verified_facts):
        if not isinstance(fact, dict):
            continue
        value = str(fact.get("figure") or fact.get("value") or "").strip()
        if not value or not any(char.isdigit() for char in value):
            continue
        if _normalise_for_match(value) in normalised_narration:
            return index, value, _label_from_fact_text(fact.get("fact"))
    return None


def _surface_anchor(region: tuple[float, float, float, float], kind: str) -> dict[str, Any]:
    """primary 표면 하단 구석의 컴팩트한 영역만 사실 문구에 내준다.

    표면 중앙을 크게 덮지 않아, 이미지 모델이 그린 메인 그래프·하락 화살표 디테일을
    가리지 않고 표면 한 귀퉁이에 적힌 깔끔한 문구처럼 보인다.
    """
    x, y, width, height = region
    anchor_width = width * 0.35
    anchor_height = height * 0.15
    anchor_x = x + width * 0.06
    anchor_y = y + height * 0.78
    return {
        "x": round(anchor_x, 4),
        "y": round(anchor_y, 4),
        "width": round(anchor_width, 4),
        "height": round(anchor_height, 4),
        "kind": kind,
    }


def plan_scene_verified_overlay(
    scene: dict[str, Any],
    archetype: str,
    information_scene: bool,
) -> list[dict[str, Any]]:
    """이 장면의 검증 수치 오버레이 계획을 만든다. 대상이 없으면 빈 목록.

    ``archetype``은 호출자가 이미지 프롬프트를 만들 때 확정한 값을 그대로
    받는다. 이 함수가 별도로 아키타입을 다시 추천하면 오버레이 좌표가
    실제로 그려진 무대와 어긋날 수 있기 때문이다.
    """
    if not information_scene:
        return []
    selected = _select_verified_fact(scene)
    if selected is None:
        return []
    kind = _OVERLAY_SURFACE_KIND_BY_ARCHETYPE.get(archetype)
    if kind is None:
        return []
    index, value, label = selected
    region = primary_surface_region(archetype)
    return [{
        "label": label,
        "value": value,
        "source_ref": f"facts[{index}]",
        "anchor": _surface_anchor(region, kind),
        "visualization": "text",
    }]
