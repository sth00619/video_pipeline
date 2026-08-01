"""V5 검증 사실을 물리 표면 합성기가 읽는 데이터 계약으로 변환한다.

이 모듈은 숫자나 금융 사실을 생성하지 않는다. 화면에 쓰는 모든 값은
``verified_facts`` 원문에 실제로 존재하는 ``v5_verified_overlays`` 값만
사용한다. 단일 수치도 사각 HUD 카드가 아니라 기존 소품의 정보면에
원근 합성할 수 있도록 ``market_chart`` 호환 payload로 바꾼다.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from app.v5.overlay.diegetic_fact_overlay import validated_facts_from_verified_scene


Direction = Literal["up", "down", "flat"]
_NUMBER_TOKEN = re.compile(r"(?<![A-Za-z])[+-]?\d[\d,]*(?:\.\d+)?%?")


def _direction(value: str, evidence: str) -> Direction:
    stripped = value.strip()
    if stripped.startswith("-"):
        return "down"
    if stripped.startswith("+"):
        return "up"
    lowered = evidence.casefold()
    if any(token in lowered for token in ("하락", "내렸다", "감소", "떨어", "down", "decline", "drop")):
        return "down"
    if any(token in lowered for token in ("상승", "올랐다", "증가", "회복", "up", "rise", "gain")):
        return "up"
    return "flat"


def _comparison_basis(fact: dict[str, Any], source_ref: str) -> str:
    published = str(fact.get("published_at") or fact.get("source_date") or "").strip()
    if published:
        return published[:64]
    return source_ref[:64]


def _surface_copy(raw_overlay: dict[str, Any], evidence: str) -> tuple[str, str]:
    """Claude가 요약한 표면 문구를 받되 새 숫자 삽입은 차단한다."""
    title = str(raw_overlay.get("surface_title") or raw_overlay.get("label") or "").strip()
    meaning = str(raw_overlay.get("surface_meaning") or "").strip()
    evidence_numbers = {
        token.replace(",", "").casefold()
        for token in _NUMBER_TOKEN.findall(evidence)
    }
    for text in (title, meaning):
        for token in _NUMBER_TOKEN.findall(text):
            if token.replace(",", "").casefold() not in evidence_numbers:
                raise ValueError("장면 표면 문구에 검증 원문에 없는 숫자가 포함됐습니다.")
    if not title:
        raise ValueError("장면 표면 제목은 비어 있을 수 없습니다.")
    return title[:40], meaning[:48]


def market_chart_from_verified_scene(scene: dict[str, Any]) -> dict[str, Any] | None:
    """검증된 단일 사실을 물리 표면용 hero-stat payload로 변환한다.

    시계열·비교·종목 묶음처럼 이미 ``market_chart``가 있는 경우에는 그
    payload가 더 풍부하고 정확하므로 이 어댑터를 사용하지 않는다.
    """
    existing = scene.get("market_chart")
    if isinstance(existing, dict):
        if existing.get("verified") is not True:
            raise ValueError("V5 정보 표면의 market_chart는 verified=true여야 합니다.")
        return existing

    rendered_facts = validated_facts_from_verified_scene(scene)
    if not rendered_facts:
        return None
    if len(rendered_facts) != 1:
        raise ValueError("단일 정보 표면에는 대표 검증 사실 한 개만 사용할 수 있습니다.")

    rendered = rendered_facts[0]
    source_index = int(rendered.source_ref.removeprefix("facts[").removesuffix("]"))
    raw_facts = scene.get("verified_facts")
    if not isinstance(raw_facts, list) or source_index >= len(raw_facts):
        raise ValueError("검증 사실 원문을 찾을 수 없습니다.")
    raw = raw_facts[source_index]
    if not isinstance(raw, dict):
        raise ValueError("검증 사실 원문 형식이 올바르지 않습니다.")

    evidence = " ".join(str(raw.get(key) or "") for key in ("fact", "figure"))
    direction = _direction(rendered.value, evidence)
    raw_overlays = scene.get("v5_verified_overlays")
    raw_overlay = raw_overlays[0] if isinstance(raw_overlays, list) and raw_overlays else {}
    if not isinstance(raw_overlay, dict):
        raise ValueError("검증 표면 문구 계약이 올바르지 않습니다.")
    surface_title, requested_meaning = _surface_copy(raw_overlay, evidence)
    meaning = requested_meaning or {
        "up": f"{rendered.label} UP",
        "down": f"{rendered.label} DOWN",
        "flat": f"{rendered.label} VERIFIED",
    }[direction]
    return {
        "verified": True,
        "source_ref": rendered.source_ref,
        "source_url": str(raw.get("source_url") or ""),
        "source_date": str(raw.get("published_at") or raw.get("source_date") or "")[:10],
        "visual_kind": "verified_fact",
        "label": surface_title,
        "hero_stat": {
            "headline_value": rendered.value,
            "headline_unit_label": rendered.label,
            "direction": direction,
            "meaning_line": meaning[:48],
            "support_marks": [],
            "comparison_basis": _comparison_basis(raw, rendered.source_ref),
            "source_refs": [rendered.source_ref],
        },
    }
