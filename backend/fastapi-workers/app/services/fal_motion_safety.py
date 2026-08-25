"""Fal/Kling에 전달할 최종 정지 이미지의 문자·수치 안전 게이트."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable

from PIL import Image, ImageOps


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
    visual_review = scene.get("visual_qa_review") or {}
    visual_review_raw = visual_review.get("raw") if isinstance(visual_review, dict) else {}
    visual_visible_texts = (
        visual_review_raw.get("visible_texts")
        if isinstance(visual_review_raw, dict) else []
    ) or []

    if visual_mode == "article_evidence" or _has_payload(scene.get("article_capture")):
        reasons.append("article_evidence")
    if scene_type in {"metric", "graph", "diagram", "text"}:
        reasons.append(f"information_scene_type:{scene_type}")
    if visual_text_policy and visual_text_policy != "strict_textless":
        reasons.append(f"visual_text_policy:{visual_text_policy}")
    if isinstance(motion_contract, dict) and motion_contract.get("eligible") is False:
        reasons.append("motion_contract_ineligible")
    # Tesseract가 만화 속 작은 영문·한글을 놓쳐도 Gemini 장면 검수에서 실제
    # 문자를 읽었다면 영상 모델이 그 표면을 다시 그리지 못하도록 정지한다.
    if any(str(value or "").strip() for value in visual_visible_texts):
        reasons.append("visual_qa_visible_text")

    for field in (
        "screen_texts",
        "screen_text_plan",
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


def _row_box(row: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Tesseract 행 좌표를 정규화한다. 테스트 주입 행처럼 좌표가 없으면 None이다."""
    try:
        left = int(row.get("left"))
        top = int(row.get("top"))
        width = int(row.get("width"))
        height = int(row.get("height"))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, left + width, top + height


def _boxes_touch(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
    """서로 다른 PSM의 분할 차이를 감안해 소폭 확장한 상자 교차를 확인한다."""
    margin = 8
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    return not (
        ax2 + margin < bx1
        or bx2 + margin < ax1
        or ay2 + margin < by1
        or by2 + margin < ay1
    )


def _confirmed_numeric_tokens(
    primary_rows: Iterable[dict[str, Any]],
    confirmation_rows: Iterable[dict[str, Any]],
) -> set[str]:
    """희소 문자 모드의 숫자를 단일 문단 모드가 같은 위치에서 재확인한다.

    만화의 서버 슬롯·창문·회로선은 PSM 11에서 ``1111``처럼 읽히기 쉽다.
    실제 화면 숫자는 PSM 6에서도 같은 위치에 숫자로 남으므로, 숫자 후보에만
    공간 교차 이중 검증을 적용한다. 문자 토큰의 기존 엄격 검사는 유지한다.
    """
    confirmation = []
    for row in confirmation_rows:
        text = str(row.get("text") or "").strip()
        if not _DIGIT_RE.search(text):
            continue
        try:
            confidence = float(row.get("conf") or -1)
        except (TypeError, ValueError):
            confidence = -1
        box = _row_box(row)
        if confidence >= 35 and box is not None:
            digits = "".join(_DIGIT_RE.findall(text))
            if digits:
                confirmation.append((digits, box))

    confirmed: set[str] = set()
    for row in primary_rows:
        text = str(row.get("text") or "").strip()
        if not _DIGIT_RE.search(text):
            continue
        box = _row_box(row)
        if box is None:
            continue
        primary_digits = "".join(_DIGIT_RE.findall(text))
        # 동전 테두리나 그래프 선을 서로 다른 숫자로 읽어도
        # 위치만 겹치면 실제 숫자로 확정하던 결함을 막는다. 두 OCR
        # 모드가 같은 숫자열과 같은 영역에 동의해야만 화면 숫자다.
        if any(
            primary_digits == other_digits and _boxes_touch(box, other_box)
            for other_digits, other_box in confirmation
        ):
            confirmed.add(text)
    return confirmed


def _read_tesseract_rows(image_path: str, *, psm: int = 11) -> tuple[str, list[dict[str, str]]]:
    executable = shutil.which("tesseract")
    if not executable:
        return "unavailable", []
    ocr_path = image_path
    temp_path = ""
    try:
        # 2K 만화 원본을 그대로 넣으면 촘촘한 선화를 문자 후보로 분할하느라
        # 장면당 30초를 넘길 수 있다. 실제 화면 문구는 960px 폭에서도 충분히
        # 남으므로 OCR 전용 축소본으로 일정한 실행 시간을 확보한다.
        with Image.open(image_path) as source:
            prepared = source.convert("L")
            if prepared.width > 960:
                ratio = 960 / prepared.width
                prepared = prepared.resize(
                    (960, max(1, round(prepared.height * ratio))),
                    Image.Resampling.LANCZOS,
                )
            prepared = ImageOps.autocontrast(prepared)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                temp_path = handle.name
            prepared.save(temp_path, "PNG", optimize=True)
            ocr_path = temp_path
        completed = subprocess.run(
            [executable, ocr_path, "stdout", "-l", "kor+eng", "--psm", str(psm), "tsv"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "failed", []
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    if completed.returncode != 0:
        return "failed", []
    # Tesseract가 장면의 선을 따옴표로 오인하면 기본 CSV 파서는 다음 TSV
    # 행까지 하나의 text 필드로 삼킨다. TSV 출력에는 인용 규칙이 없으므로
    # QUOTE_NONE으로 읽어 OCR 감사 행의 경계를 그대로 보존한다.
    return "completed", list(csv.DictReader(
        io.StringIO(completed.stdout), delimiter="\t", quoting=csv.QUOTE_NONE,
    ))


def inspect_visible_text(
    image_path: str,
    *,
    ocr_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """최종 래스터에서 모델이 만든 읽을 수 있는 문자·숫자를 검사한다.

    Fal 후보 검사와 생성 이미지 승인 검사가 같은 OCR 임계값을 사용해야 한
    단계에서 허용한 글자를 다음 단계가 다르게 해석하지 않는다.
    """
    confirmation_status = "not_required"
    if ocr_rows is None:
        status, rows = _read_tesseract_rows(image_path)
        tokens = _meaningful_ocr_tokens(rows) if status == "completed" else []
        if status == "completed" and any(_DIGIT_RE.search(token) for token in tokens):
            confirmation_status, confirmation_rows = _read_tesseract_rows(image_path, psm=6)
            if confirmation_status == "completed":
                confirmed = _confirmed_numeric_tokens(rows, confirmation_rows)
                tokens = [
                    token for token in tokens
                    if not _DIGIT_RE.search(token) or token in confirmed
                ]
    else:
        status, rows = "completed", list(ocr_rows)
        # 단위 테스트와 외부 OCR 주입은 이미 한 번 검증된 행으로 취급한다.
        tokens = _meaningful_ocr_tokens(rows)
        confirmation_status = "provided_rows"
    return {
        "status": status,
        "visible_tokens": tokens,
        "numeric_confirmation_status": confirmation_status,
    }


def _image_identity(image_path: str) -> dict[str, int | str] | None:
    try:
        with open(image_path, "rb") as image_file:
            stat = os.fstat(image_file.fileno())
            sha256 = hashlib.sha256(image_file.read()).hexdigest()
    except OSError:
        return None
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": sha256,
    }


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
        inspection = inspect_visible_text(image_path, ocr_rows=ocr_rows)
        ocr_status = str(inspection["status"])
        if ocr_status == "unavailable":
            reasons.append("ocr_unavailable")
        elif ocr_status == "failed":
            reasons.append("ocr_failed")
        else:
            visible_tokens = list(inspection["visible_tokens"])
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
