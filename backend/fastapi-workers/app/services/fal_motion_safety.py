"""Fal/Kling에 전달할 최종 정지 이미지의 문자·수치 안전 게이트."""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
from typing import Any, Iterable


FAL_MOTION_SAFETY_POLICY_VERSION = 1
_MEANINGFUL_TEXT_RE = re.compile(r"[A-Za-z가-힣]")
_DIGIT_RE = re.compile(r"\d")


def _has_payload(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def fal_motion_metadata_block_reasons(scene: dict) -> list[str]:
    """이미지에 문자·수치 표면이 있음을 뜻하는 명시 메타데이터를 찾는다."""
    reasons: list[str] = []
    visual_mode = str(
        scene.get("visual_mode")
        or (scene.get("v5_render_contract") or {}).get("visual_mode")
        or ""
    ).strip().lower()
    scene_type = str(scene.get("scene_type") or "").strip().lower()
    visual_text_policy = str(
        scene.get("visual_text_policy")
        or (scene.get("v5_render_contract") or {}).get("visual_text_policy")
        or ""
    ).strip().lower()
    motion_contract = scene.get("motion_contract")

    if visual_mode == "article_evidence" or _has_payload(scene.get("article_capture")):
        reasons.append("article_evidence")
    if scene_type in {"metric", "graph", "diagram", "text"}:
        reasons.append(f"information_scene_type:{scene_type}")
    if visual_text_policy and visual_text_policy != "strict_textless":
        reasons.append(f"visual_text_policy:{visual_text_policy}")
    if isinstance(motion_contract, dict) and motion_contract.get("eligible") is False:
        reasons.append("motion_contract_ineligible")

    for field in (
        "core_figures",
        "market_chart",
        "index_data",
        "v5_verified_overlays",
        "info_surface_plan",
        "final_image_path",
    ):
        if _has_payload(scene.get(field)):
            reasons.append(field)

    # 동일 원인이 여러 계약에서 잡혀도 감사 로그는 한 번만 남긴다.
    return list(dict.fromkeys(reasons))


def _meaningful_ocr_tokens(rows: Iterable[dict[str, Any]]) -> list[str]:
    """도형 오인식은 버리고 실제 숫자·단어로 볼 수 있는 OCR 토큰만 남긴다."""
    tokens: list[str] = []
    for row in rows:
        raw = str(row.get("text") or "").strip()
        if not raw:
            continue
        try:
            confidence = float(row.get("conf") or -1)
        except (TypeError, ValueError):
            confidence = -1
        compact = re.sub(r"\s+", "", raw)
        if _DIGIT_RE.search(compact) and confidence >= 35:
            tokens.append(raw)
            continue
        letters = "".join(_MEANINGFUL_TEXT_RE.findall(compact))
        if len(letters) >= 3 and confidence >= 70:
            tokens.append(raw)
    return list(dict.fromkeys(tokens))[:20]


def _read_tesseract_rows(image_path: str) -> tuple[str, list[dict[str, str]]]:
    executable = shutil.which("tesseract")
    if not executable:
        return "unavailable", []
    try:
        completed = subprocess.run(
            [executable, image_path, "stdout", "-l", "kor+eng", "--psm", "11", "tsv"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "failed", []
    if completed.returncode != 0:
        return "failed", []
    return "completed", list(csv.DictReader(io.StringIO(completed.stdout), delimiter="\t"))


def _image_identity(image_path: str) -> dict[str, int] | None:
    try:
        stat = os.stat(image_path)
    except OSError:
        return None
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def fal_motion_safety_is_current(scene: dict, image_path: str) -> bool:
    safety = scene.get("fal_motion_safety")
    return bool(
        isinstance(safety, dict)
        and safety.get("policy_version") == FAL_MOTION_SAFETY_POLICY_VERSION
        and safety.get("image_identity") == _image_identity(image_path)
        and (
            safety.get("eligible") is False
            or (safety.get("ocr") or {}).get("status") == "completed"
        )
    )


def assess_fal_motion_safety(
    scene: dict,
    image_path: str,
    *,
    scan_image: bool = True,
    ocr_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """메타데이터와 최종 PNG를 모두 통과한 장면만 Fal 대상으로 승인한다."""
    reasons = fal_motion_metadata_block_reasons(scene)
    identity = _image_identity(image_path)
    ocr_status = "skipped_metadata_block" if reasons else "not_requested"
    visible_tokens: list[str] = []

    if identity is None:
        reasons.append("source_image_missing")
        ocr_status = "missing_image"
    elif not reasons and scan_image:
        if ocr_rows is None:
            ocr_status, rows = _read_tesseract_rows(image_path)
        else:
            ocr_status, rows = "completed", list(ocr_rows)
        if ocr_status == "unavailable":
            reasons.append("ocr_unavailable")
        elif ocr_status == "failed":
            reasons.append("ocr_failed")
        else:
            visible_tokens = _meaningful_ocr_tokens(rows)
            if visible_tokens:
                reasons.append("visible_text_or_number")

    reasons = list(dict.fromkeys(reasons))
    return {
        "policy_version": FAL_MOTION_SAFETY_POLICY_VERSION,
        "eligible": not reasons,
        "reasons": reasons,
        "motion_target": "character" if bool(scene.get("character_required", True)) else "non_text_prop",
        "image_identity": identity,
        "ocr": {"status": ocr_status, "visible_tokens": visible_tokens},
    }
