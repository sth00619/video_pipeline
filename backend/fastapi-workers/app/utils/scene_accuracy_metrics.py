"""이미지 검수의 항목 정확도와 장면 완전정확도를 분리해 집계한다.

IGenBench의 질문 단위/이미지 단위 분리에서 검증 방법만 차용한다. 외부 벤치마크의
명칭이나 점수를 그대로 주장하지 않고, 운영 장면의 현재 계약을 명시적 상태로 집계한다.
"""
from __future__ import annotations

from typing import Any


_VALID_STATUSES = {"pass", "fail", "pending", "not_applicable"}


def _status(value: Any) -> str:
    status = str(value).strip().lower()
    if status not in _VALID_STATUSES:
        raise ValueError(f"지원하지 않는 이미지 검수 상태: {value}")
    return status


def aggregate_scene_accuracy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """pass/fail만 항목 정확도에 넣고 pending은 장면 승인을 차단한다."""
    scene_rows: list[dict[str, Any]] = []
    counts = {name: 0 for name in _VALID_STATUSES}
    per_item_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        items = {str(key): _status(value) for key, value in (row.get("items") or {}).items()}
        for name, status in items.items():
            counts[status] += 1
            item_counts = per_item_counts.setdefault(
                name,
                {state: 0 for state in _VALID_STATUSES},
            )
            item_counts[status] += 1
        evaluated = [status for status in items.values() if status in {"pass", "fail"}]
        fully_accurate = bool(evaluated) and all(
            status in {"pass", "not_applicable"} for status in items.values()
        )
        scene_rows.append({
            "scene_key": str(row.get("scene_key") or ""),
            "items": items,
            "fully_accurate": fully_accurate,
        })

    evaluated_count = counts["pass"] + counts["fail"]
    scene_count = len(scene_rows)
    fully_accurate_count = sum(1 for row in scene_rows if row["fully_accurate"])
    per_item = {}
    for name in sorted(per_item_counts):
        item_counts = per_item_counts[name]
        item_evaluated = item_counts["pass"] + item_counts["fail"]
        per_item[name] = {
            "evaluated_count": item_evaluated,
            "passed_count": item_counts["pass"],
            "failed_count": item_counts["fail"],
            "pending_count": item_counts["pending"],
            "not_applicable_count": item_counts["not_applicable"],
            "accuracy": item_counts["pass"] / item_evaluated if item_evaluated else None,
        }
    return {
        "contract": "scene-accuracy-metrics-v1",
        "scene_count": scene_count,
        "evaluated_item_count": evaluated_count,
        "passed_item_count": counts["pass"],
        "failed_item_count": counts["fail"],
        "pending_item_count": counts["pending"],
        "not_applicable_item_count": counts["not_applicable"],
        "item_accuracy": counts["pass"] / evaluated_count if evaluated_count else None,
        "fully_accurate_scene_count": fully_accurate_count,
        "fully_accurate_scene_rate": fully_accurate_count / scene_count if scene_count else None,
        "per_item": per_item,
        "scenes": scene_rows,
    }


def visual_qa_item_results(failure_categories: list[str]) -> dict[str, str]:
    """공통 비전 QA 실패 범주를 서로 독립적인 품질 항목으로 정규화한다."""
    failures = {str(value) for value in failure_categories}

    def verdict(*prefixes: str) -> str:
        return "fail" if any(
            failure == prefix or failure.startswith(prefix)
            for failure in failures
            for prefix in prefixes
        ) else "pass"

    return {
        "text_integrity": verdict("text_", "speech_bubble_"),
        "deterministic_numeric_integrity": verdict(
            "text_missing_approved_numeric",
            "text_unapproved_numeric",
            "deterministic_numeric_",
        ),
        "scene_meaning": verdict("scene_semantic", "scene_required_props", "number_panel_only"),
        "character_anatomy_and_face": verdict("character_"),
        "style_fidelity": verdict("style_", "visual_medium"),
        "composition_and_density": verdict("scene_information_density", "scene_composition"),
        "physical_text_surface": verdict("text_surface_", "deterministic_surface_"),
        "unexpected_visual_anomaly": verdict(
            "unexpected_or_ambiguous_prop",
            "local_edit_blur_smear_artifact",
        ),
        "unlisted_failure_scan": verdict(
            "unexpected_or_ambiguous_prop",
            "local_edit_blur_smear_artifact",
        ),
    }
