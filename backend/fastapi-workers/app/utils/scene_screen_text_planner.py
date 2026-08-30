"""승인 대본에서 장면 로컬 화면 문구만 결정론적으로 고른다.

이미지의 모든 문자를 없애는 대신, 승인 내레이션에 실제로 있는 회사명·지수명·
핵심 금융 용어와 수치 표현만 씬 단위 허용 목록으로 만든다. 숫자는 이후
Pillow/FFmpeg 표면 렌더러가 담당하며 이미지 모델에는 직접 쓰게 하지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.utils.entity_english_map import get_entity_info


_QUOTED_PHRASE_RE = re.compile(r"['\"“”‘’](?P<text>[^'\"“”‘’\n]{2,32})['\"“”‘’]")
_NUMBER = r"[+-]?\d[\d,]*(?:\.\d+)?"
_RANGE_JOIN = r"(?:에서|~|∼|〜|–|—|-)"
_FINANCIAL_VALUE_RE = re.compile(
    r"(?:"
    + _NUMBER + r"\s*조\s*" + _RANGE_JOIN + r"\s*" + _NUMBER + r"\s*조\s*원?"
    r"|" + _NUMBER + r"\s*" + _RANGE_JOIN + r"\s*" + _NUMBER + r"\s*(?:퍼센트포인트|퍼센트|포인트|%p|%)"
    r"|" + _NUMBER + r"\s*만\s*" + _NUMBER + r"\s*원"
    r"|" + _NUMBER + r"\s*조(?:\s*" + _NUMBER + r"\s*억)?(?:\s*" + _NUMBER + r"\s*만)?\s*원?"
    r"|" + _NUMBER + r"\s*억(?:\s*" + _NUMBER + r"\s*만)?\s*(?:원|주)?"
    r"|(?:PER\s*)?" + _NUMBER + r"\s*배"
    r"|" + _NUMBER + r"\s*(?:퍼센트포인트|퍼센트|포인트|%p|%|만\s*원|원)"
    r")"
)

# 승인 대본에 실제로 등장할 때만 사용한다. 이 목록은 문구를 새로 만드는
# 사전이 아니라, 긴 내레이션에서 화면에 유용한 원문 토큰을 고르는 필터다.
_DISPLAY_TERMS = (
    "삼성전자",
    "SK하이닉스",
    "코스피",
    "코스닥",
    "주주환원",
    "원달러 환율",
    "외국인",
    "거래대금",
    "거래량",
    "반도체",
    "IR",
    # 시장 전망·리스크 설명에서 장면의 핵심 대비를 이루는 일반 용어다.
    # 특정 작업 번호용 문구가 아니라 승인 내레이션에 실제로 있을 때만
    # 선택되는 공통 화면 어휘이며, 임의 문구 생성에는 사용하지 않는다.
    "엇갈림",
    "대형주",
    "경고",
    "전망치",
)


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)


def _scene_narration(scene: dict[str, Any]) -> str:
    return str(
        scene.get("text_for_tts")
        or scene.get("content")
        or scene.get("text")
        or scene.get("narration")
        or ""
    ).strip()


def derive_scene_screen_texts(scene: dict[str, Any], *, limit: int = 4) -> list[str]:
    """기존 명시 문구를 보존하고, 비어 있을 때만 승인 원문에서 최대 4개를 고른다."""
    existing = [str(value).strip() for value in (scene.get("screen_texts") or []) if str(value).strip()]
    if existing:
        return existing

    narration = _scene_narration(scene)
    if not narration:
        return []

    candidates: list[tuple[int, int, str]] = []
    for match in _QUOTED_PHRASE_RE.finditer(narration):
        candidates.append((0, match.start(), match.group("text").strip()))
    for term in _DISPLAY_TERMS:
        start = narration.find(term)
        if start >= 0:
            candidates.append((1, start, term))
    for match in _FINANCIAL_VALUE_RE.finditer(narration):
        candidates.append((2, match.start(), match.group(0).strip()))

    selected: list[str] = []
    for _priority, _position, value in sorted(candidates, key=lambda item: (item[0], item[1])):
        key = _compact(value)
        if not key:
            continue
        # 인용구가 "10퍼센트 족쇄"를 이미 포함하면 "10퍼센트"를 또 쓰지 않는다.
        if any(key in _compact(item) or _compact(item) in key for item in selected):
            continue
        selected.append(value)
        if len(selected) >= max(0, int(limit)):
            break
    return selected


_COMPANY_CATEGORIES = {"kospi_large", "kosdaq_mid", "us_tech"}


def _shared_surface_regions(count: int) -> list[list[float]]:
    """한 물리 화면 안에서 문구 수만큼 겹치지 않는 상대 영역을 만든다."""
    count = max(1, int(count))
    gap = 0.04
    outer_y = 0.08
    usable = 1.0 - outer_y * 2 - gap * (count - 1)
    height = usable / count
    return [
        [0.08, round(outer_y + index * (height + gap), 4), 0.84, round(height, 4)]
        for index in range(count)
    ]


def derive_scene_screen_text_plan(
    scene: dict[str, Any],
    screen_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """승인 문구를 장면 의미 사물과 그 물리 표면에 결정론적으로 배정한다.

    이 함수는 픽셀 좌표를 추측하지 않는다. 이미지 생성 전 프롬프트가 필요한
    사물과 표면을 만들도록 의미 ID를 부여하고, 실제 좌표는 생성 후 표면 검출과
    attestation이 담당한다. 특정 작업·scene 번호는 사용하지 않는다.
    """
    texts = [str(value).strip() for value in (screen_texts or []) if str(value).strip()]
    if not texts:
        return []

    classified: list[tuple[str, str]] = []
    for text in texts:
        info = get_entity_info(text)
        if any(character.isdigit() for character in text):
            role = "numeric_fact"
        elif info and info.category in _COMPANY_CATEGORIES:
            role = "company"
        elif info and info.category == "index_exchange":
            role = "market_index"
        else:
            role = "context_label"
        classified.append((text, role))

    company_total = sum(role == "company" for _, role in classified)
    summary_total = sum(role in {"market_index", "numeric_fact"} for _, role in classified)
    summary_regions = iter(_shared_surface_regions(summary_total))
    company_position = 0
    context_position = 0
    plan: list[dict[str, Any]] = []
    render = scene.get("v5_render_contract") or {}
    selection = render.get("selection") or scene.get("v5_scene_type_selection") or {}
    archetype = str(
        selection.get("archetype")
        or scene.get("archetype")
        or scene.get("visual_archetype")
        or ""
    ).strip()
    for text, role in classified:
        if archetype == "trade_calculator" and company_total >= 2:
            if role == "company":
                company_position += 1
                side = {1: "left", 2: "right"}.get(company_position, str(company_position))
                plan.append({
                    "text": text,
                    "purpose": "information",
                    "semantic_object_id": f"comparison_entity_{company_position}",
                    "visual_device_id": "balance_scale",
                    "surface_id": f"balance_scale_{side}_pan_label",
                    "surface": f"balance_scale_{side}_pan_label",
                    "surface_kind": "prop_panel",
                    "capacity": 1,
                    "max_occurrences": 1,
                })
                continue
            if role == "numeric_fact":
                plan.append({
                    "text": text,
                    "purpose": "information",
                    "semantic_object_id": "comparison_metric",
                    "visual_device_id": "balance_scale",
                    "surface_id": "balance_scale_plinth",
                    "surface": "balance_scale_plinth",
                    "surface_kind": "prop_panel",
                    "capacity": 1,
                    "max_occurrences": 1,
                })
                continue
        if role == "company":
            company_position += 1
            if company_total == 1:
                object_id, surface_id = "subject_entity", "subject_prop"
            else:
                side = {1: "left", 2: "right"}.get(company_position, str(company_position))
                object_id = f"comparison_entity_{company_position}"
                surface_id = f"comparison_prop_{side}"
            item = {
                "text": text,
                "purpose": "information",
                "semantic_object_id": object_id,
                "surface_id": surface_id,
                "surface": surface_id,
                "surface_kind": "prop_panel",
                "capacity": 1,
                "max_occurrences": 1,
            }
        elif role in {"market_index", "numeric_fact"}:
            item = {
                "text": text,
                "purpose": "information",
                "semantic_object_id": "market_summary",
                "surface_id": "summary_monitor",
                "surface": "summary_monitor",
                "surface_kind": "device_screen",
                "capacity": summary_total,
                "max_occurrences": 1,
            }
            if summary_total > 1:
                item["region"] = next(summary_regions)
        else:
            context_position += 1
            item = {
                "text": text,
                "purpose": "information",
                "semantic_object_id": f"context_concept_{context_position}",
                "surface_id": f"context_sign_{context_position}",
                "surface": f"context_sign_{context_position}",
                "surface_kind": "signboard",
                "capacity": 1,
                "max_occurrences": 1,
            }
        plan.append(item)
    return plan


def attach_scene_screen_texts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """장면 순서와 승인 내레이션을 바꾸지 않고 화면 문구 계약만 보완한다."""
    planned: list[dict[str, Any]] = []
    for source in scenes or []:
        scene = dict(source)
        previous_source = str(source.get("screen_text_source") or "")
        if previous_source.startswith("approved_narration_exact_extract_"):
            # 자동 추출 규칙이 개선된 경우 과거 v1의 잘린 복합 수치(예:
            # ``25만 7000원`` → ``7000원``)를 명시 계약처럼 고정하지 않는다.
            # 사람이 작성한 explicit_scene_contract는 계속 그대로 보존한다.
            scene["screen_texts"] = []
        scene["screen_texts"] = derive_scene_screen_texts(scene)
        scene["screen_text_source"] = (
            "explicit_scene_contract"
            if source.get("screen_texts") and not previous_source.startswith("approved_narration_exact_extract_")
            else "approved_narration_exact_extract_v3"
        )
        previous_plan_source = str(source.get("screen_text_plan_source") or "")
        explicit_plan = source.get("screen_text_plan")
        if explicit_plan and not previous_plan_source.startswith("approved_narration_semantic_surface_plan_"):
            scene["screen_text_plan"] = [dict(item) for item in explicit_plan if isinstance(item, dict)]
            scene["screen_text_plan_source"] = "explicit_scene_contract"
        else:
            scene["screen_text_plan"] = derive_scene_screen_text_plan(scene, scene["screen_texts"])
            scene["screen_text_plan_source"] = "approved_narration_semantic_surface_plan_v1"
        planned.append(scene)
    return planned
