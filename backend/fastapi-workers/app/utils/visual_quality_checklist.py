"""이미지 자동 계측과 육안 판정을 하나의 공통 항목 계약으로 묶는다."""
from __future__ import annotations

from typing import Any

from app.utils.scene_accuracy_metrics import aggregate_scene_accuracy


VISUAL_QUALITY_CHECKLIST_VERSION = "visual-quality-checklist-v1"
VISUAL_QUALITY_ITEMS = (
    "text_integrity",
    "deterministic_numeric_integrity",
    "physical_text_surface",
    "scene_meaning",
    "character_anatomy_and_face",
    "style_fidelity",
    "composition_and_density",
    "unexpected_visual_anomaly",
    "unlisted_failure_scan",
)
_VALID_STATUSES = {"pass", "fail", "pending", "not_applicable"}


def _validated_updates(values: dict[str, Any] | None) -> dict[str, str]:
    updates: dict[str, str] = {}
    for name, raw_status in (values or {}).items():
        if name not in VISUAL_QUALITY_ITEMS:
            raise ValueError(f"지원하지 않는 이미지 체크리스트 항목: {name}")
        status = str(raw_status).strip().lower()
        if status not in _VALID_STATUSES:
            raise ValueError(f"지원하지 않는 이미지 체크리스트 상태: {raw_status}")
        updates[name] = status
    return updates


def build_visual_quality_checklist(
    scene_key: str,
    *,
    automated: dict[str, Any] | None = None,
    user_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """자동 결과와 사용자 결과를 합치되 미판정 항목은 절대 통과시키지 않는다."""
    items = {name: "pending" for name in VISUAL_QUALITY_ITEMS}
    items.update(_validated_updates(automated))
    items.update(_validated_updates(user_review))
    fully_accurate = all(status in {"pass", "not_applicable"} for status in items.values())
    return {
        "contract": VISUAL_QUALITY_CHECKLIST_VERSION,
        "scene_key": str(scene_key),
        "items": items,
        "fully_accurate": fully_accurate,
        "approval_blocked": not fully_accurate,
    }


def aggregate_visual_quality_checklists(checklists: list[dict[str, Any]]) -> dict[str, Any]:
    """항목별 정확도와 전체 장면 완전승인율을 항상 함께 반환한다."""
    return aggregate_scene_accuracy([
        {
            "scene_key": str(checklist.get("scene_key") or ""),
            "items": dict(checklist.get("items") or {}),
        }
        for checklist in checklists
    ])
