"""롱폼 장면의 자막 외 편집 문구를 차단하고 판단 근거만 남긴다.

대본 의미는 V5의 장면 속 소품·그래프·상황으로 전달한다. 영상 후처리에서
만드는 말풍선·요약칩·카드 문구는 자막과 경쟁하고 장면 밖에 떠 보이므로
생성하지 않는다.
"""
from __future__ import annotations

from typing import Any

_WARNING = ("경고", "위기", "충격", "급락", "폭락", "하락", "불안", "리스크", "부담", "악화")
_EXPLAIN = ("왜", "이유", "원인", "구조", "어떻게", "의미", "핵심", "흐름", "영향", "때문")
_COMPARE = ("비교", "대비", "차이", "반면", "vs", "대결")
_EMPHATIC_POSES = {"surprised", "worried", "pointing", "thinking", "explaining"}


def _intent(scene: dict[str, Any]) -> str:
    text = " ".join(str(scene.get(key) or "") for key in ("title", "content", "bubble_text")).lower()
    if any(token in text for token in _WARNING):
        return "warning"
    if any(token in text for token in _COMPARE):
        return "comparison"
    if any(token in text for token in _EXPLAIN):
        return "explanation"
    if "?" in text or str(scene.get("section") or "") in {"intro", "conclusion"}:
        return "hook"
    if str(scene.get("pose") or "") in _EMPHATIC_POSES:
        return "reaction"
    return "none"


def _overlay_spec(scene: dict[str, Any], intent: str) -> tuple[str, str, str, str]:
    """Return kind, message role, anchor and tone for a selected scene."""
    section = str(scene.get("section") or "scenario")
    if section == "intro":
        return ("burst", "hook", "subject_gaze", "danger" if intent == "warning" else "warning")
    if section == "conclusion":
        return ("caption_chip", "takeaway", "upper_left", "benefit")
    if section == "background":
        family = str((scene.get("art_direction") or {}).get("family") or "")
        if family == "history_classroom" and intent == "explanation":
            return ("chalk_note", "cause", "target", "neutral")
        if intent in {"explanation", "comparison"}:
            return ("cloud", "cause", "target", "neutral")
        return ("caption_chip", "cause" if intent == "explanation" else "evidence_quote", "upper_left", "neutral")
    if section == "action":
        return ("caption_chip", "decision", "subject_hand", "warning" if intent == "warning" else "neutral")
    if intent in {"explanation", "comparison"}:
        return ("cloud", "cause", "target", "neutral")
    return ("speech", "cause" if intent == "explanation" else "reaction", "subject_gaze", "warning" if intent == "warning" else "neutral")


def direct_editorial_overlays(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """자막 외 텍스트 오버레이를 전면 비활성화하고 산출물 계보에 기록한다."""
    for index, scene in enumerate(scenes):
        previous_plan = scene.pop("editorial_overlay_plan", None)
        decision: dict[str, Any] = {
            "index": index,
            "selected": False,
            "reason": "script_caption_only_policy",
            "policy_version": "v5-script-caption-only-20260803",
        }
        if previous_plan is not None or scene.get("bubble_text") or scene.get("data_overlay_plan"):
            decision["suppressed_non_subtitle_overlay"] = True
        scene["editorial_decision"] = decision
    return scenes
