"""유료 이미지 canary의 사용자 육안 검토를 fail-closed로 기록한다."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.utils.visual_judgment_disagreement_log import compare_visual_judgments


CANARY_VISUAL_REVIEW_VERSION = "canary-visual-review-v2"
REQUIRED_VISUAL_CHECKS = (
    "character_anatomy",
    "style_fidelity",
    "scene_meaning_legibility",
    "text_and_physical_surface",
    "unexpected_visual_artifacts",
    "unexpected_or_ambiguous_props",
    "unlisted_failure_scan",
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_canary_visual_review_packet(
    image_path: str | Path,
    image_sha256: str,
    *,
    automated_findings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """자동 계측과 별개인 사용자 육안 판정을 위한 보류 객체를 만든다."""
    path = Path(image_path).resolve()
    actual_sha256 = _file_sha256(path)
    if actual_sha256 != str(image_sha256):
        raise ValueError("canary 이미지 SHA-256이 실물과 일치하지 않습니다.")
    return {
        "version": CANARY_VISUAL_REVIEW_VERSION,
        "status": "pending_user_visual_review",
        "user_visual_review_required": True,
        "image_attachment_required": True,
        "approval_blocked": True,
        "image_path": str(path),
        "image_sha256": actual_sha256,
        "required_checks": [
            {"name": name, "status": "pending"}
            for name in REQUIRED_VISUAL_CHECKS
        ],
        "automated_findings": dict(automated_findings or {}),
        "allowed_pre_user_verdicts": ["pending", "rejected"],
        "note": (
            "자동 얼굴·OCR·표면 계측을 유지하되, 실물 첨부 후 사용자가 해부학·화풍·"
            "장면 의미를 확인하기 전에는 개선됨 또는 승인 근접으로 판정하지 않는다."
        ),
    }


def record_canary_user_visual_review(
    packet: dict[str, Any],
    decisions: dict[str, bool],
    *,
    reviewer: str,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    """모든 필수 육안 항목에 대한 명시적 사용자 판정을 기록한다."""
    missing = [name for name in REQUIRED_VISUAL_CHECKS if name not in decisions]
    if missing:
        raise ValueError("누락된 canary 육안 판정: " + ", ".join(missing))
    checks = [
        {"name": name, "status": "pass" if decisions[name] else "fail"}
        for name in REQUIRED_VISUAL_CHECKS
    ]
    passed = all(decisions[name] is True for name in REQUIRED_VISUAL_CHECKS)
    agreement = compare_visual_judgments(packet.get("automated_findings"), decisions)
    return {
        **packet,
        "status": "user_visual_review_passed" if passed else "rejected_by_user_visual_review",
        "approval_blocked": not passed,
        "reviewer": str(reviewer),
        "required_checks": checks,
        "unexpected_findings": [str(value) for value in (findings or []) if str(value).strip()],
        "judgment_agreement": agreement,
        "judgment_disagreements": agreement["disagreements"],
    }
