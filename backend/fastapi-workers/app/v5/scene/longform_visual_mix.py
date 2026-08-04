"""대본 장면 계보를 유지한 채 기사형·일반형·정보형 비율을 배정한다."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _is_article(scene: dict[str, Any]) -> bool:
    return bool(scene.get("article_capture")) or str(scene.get("visual_kind") or "") in {
        "article_evidence", "article_scene",
    }


def _information_score(scene: dict[str, Any], index: int) -> tuple[int, int]:
    """정보형이 특히 유용한 장면을 먼저 고르되, 나머지도 상황형으로 남긴다."""
    scene_type = str(scene.get("scene_type") or "").lower()
    text = " ".join(str(scene.get(key) or "") for key in ("title", "content", "text")).lower()
    score = 0
    if scene_type in {"metric", "graph", "diagram", "text"}:
        score += 3
    if any(token in text for token in ("비교", "영향", "구조", "흐름", "원인", "변수", "관계", "점검")):
        score += 2
    if any(token in text for token in ("반도체", "환율", "금리", "실적", "수급", "섹터")):
        score += 1
    # 동점이면 대본 순서상 간격을 유지해 같은 구도가 몰리지 않게 한다.
    return score, -index


def apply_longform_visual_mix(scenes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """전체 롱폼에서 세 시각 유형을 함께 쓰도록 명시 모드를 붙인다.

    기사형은 검증된 캡처가 이미 붙은 장면만 사용한다. 일반형은 글자 없는
    상황 일러스트, 정보형은 대본 의미를 소품 표면 한 곳에 넣는 V5 계약으로
    이어진다. 이 함수는 내레이션과 이미지 프롬프트를 만들거나 변경하지 않는다.
    """
    planned = [dict(scene) for scene in scenes]
    article_indexes = [index for index, scene in enumerate(planned) if _is_article(scene)]
    candidates = [index for index in range(len(planned)) if index not in article_indexes]
    target_info = max(1, round(len(candidates) * 0.34)) if candidates else 0
    ranked = sorted(candidates, key=lambda index: _information_score(planned[index], index), reverse=True)
    info_indexes = set(ranked[:target_info])

    for index, scene in enumerate(planned):
        if index in article_indexes:
            scene["visual_mode"] = "article_evidence"
            scene["visual_mix_role"] = "article"
        elif index in info_indexes:
            scene["visual_mode"] = "archetype_explainer"
            scene["visual_mix_role"] = "information"
        else:
            scene["visual_mode"] = "semantic_illustration"
            scene["visual_mix_role"] = "general"

    counts = Counter(str(scene["visual_mode"]) for scene in planned)
    return planned, {
        "version": "longform-three-visual-mix-v1",
        "scene_count": len(planned),
        "counts": dict(sorted(counts.items())),
        "article_scene_ids": [str(planned[index].get("scene_id") or index) for index in article_indexes],
        "information_scene_ids": [str(planned[index].get("scene_id") or index) for index in sorted(info_indexes)],
        "semantic_scene_ids": [
            str(scene.get("scene_id") or index)
            for index, scene in enumerate(planned)
            if scene["visual_mode"] == "semantic_illustration"
        ],
    }
