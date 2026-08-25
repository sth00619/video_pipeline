"""최종 이미지에 합성된 승인 문구를 OCR 결과와 대조한다.

이 모듈은 텍스트를 누가 썼는지를 합격 기준으로 삼지 않는다. V5 결정론 표면
경로에서 Pillow가 합성하도록 계약된 대본 문구·검증 사실이 최종 프레임에서
정확히 읽히는지를 확인한다. 이미지 모델이 직접 쓰는 비수치 승인 문자열은
장면 로컬 텍스트 계약과 멀티모달 시각 QA가 별도로 검수한다.
"""
from __future__ import annotations

import os
import re
import tempfile
import hashlib
from typing import Any, Iterable

from PIL import Image, ImageOps

from app.services.fal_motion_safety import _read_tesseract_rows


class FinalFrameTextIntegrityError(RuntimeError):
    """최종 프레임의 문구가 예정 문구와 일치하지 않을 때 발생한다."""


def _normalise(value: Any) -> str:
    # 오탈자·숫자 변형을 숨기지 않는다. OCR 줄바꿈과 공백만 제거한다.
    return re.sub(r"\s+", "", str(value or "")).strip()


def expected_final_frame_texts(scene: dict[str, Any]) -> list[str]:
    """결정론 렌더러가 이 장면에 실제로 써야 하는 문자열을 반환한다."""
    overlays = scene.get("v5_verified_overlays")
    expected: list[str] = []
    if isinstance(overlays, list) and overlays:
        for overlay in overlays:
            if not isinstance(overlay, dict):
                continue
            for key in ("label", "value"):
                text = str(overlay.get(key) or "").strip()
                if text:
                    expected.append(text)
    else:
        contract = scene.get("v5_render_contract")
        if isinstance(contract, dict) and contract.get("visual_text_policy") == "deterministic_surface_text":
            caption = contract.get("surface_caption")
            if isinstance(caption, dict):
                texts = caption.get("texts")
                if isinstance(texts, list) and texts:
                    expected.extend(str(text).strip() for text in texts if str(text).strip())
                else:
                    text = str(caption.get("korean") or "").strip()
                    if text:
                        expected.append(text)
    return list(dict.fromkeys(expected))


def inspect_final_frame_text_integrity(
    image_path: str,
    scene: dict[str, Any],
    *,
    ocr_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """예정 문구가 최종 래스터에서 글자·숫자 그대로 읽히는지 검사한다."""
    expected = expected_final_frame_texts(scene)
    if not expected:
        return {
            "status": "not_applicable",
            "passed": True,
            "expected": [],
            "recognized": [],
            "missing_or_altered": [],
        }

    if ocr_rows is None:
        status, rows = _read_expected_regions(image_path, scene)
    else:
        status, rows = "completed", list(ocr_rows)
    if status != "completed":
        return {
            "status": status,
            "passed": False,
            "expected": expected,
            "recognized": [],
            "missing_or_altered": expected,
        }

    recognized = [
        str(row.get("text") or "").strip()
        for row in rows
        if str(row.get("text") or "").strip()
    ]
    joined = _normalise(" ".join(recognized))
    missing = [text for text in expected if _normalise(text) not in joined]
    provenance = _inspect_deterministic_render_provenance(image_path, scene, expected)
    # Tesseract는 정자형 한글도 `억/열`처럼 오판할 수 있다. 승인 문자열과
    # 렌더 직후 픽셀 영역 해시가 모두 일치할 때만 OCR 오판을 보완한다.
    # 생성 모델이 직접 쓴 문구에는 이 예외가 적용되지 않는다.
    passed = not missing or bool(provenance.get("passed"))
    return {
        "status": status,
        "passed": passed,
        "ocr_passed": not missing,
        "deterministic_provenance": provenance,
        "expected": expected,
        "recognized": recognized,
        "missing_or_altered": [] if passed else missing,
        "ocr_missing_or_altered": missing,
    }


def _inspect_deterministic_render_provenance(
    image_path: str,
    scene: dict[str, Any],
    expected: list[str],
) -> dict[str, Any]:
    """승인 문구와 렌더 직후 픽셀이 모두 동일할 때만 OCR 오판을 보완한다."""
    rendered = scene.get("deterministic_text_regions")
    if not isinstance(rendered, list) or not rendered:
        return {"passed": False, "reason": "metadata_missing"}
    expected_hash = hashlib.sha256("\n".join(expected).encode("utf-8")).hexdigest()
    try:
        with Image.open(image_path) as source:
            rgb = source.convert("RGB")
            for item in rendered:
                if not isinstance(item, dict):
                    continue
                bbox = item.get("bbox")
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue
                if str(item.get("text_sha256") or "") != expected_hash:
                    continue
                crop = rgb.crop(tuple(int(value) for value in bbox))
                current_hash = hashlib.sha256(crop.tobytes()).hexdigest()
                if current_hash != str(item.get("rendered_crop_sha256") or ""):
                    continue
                if int(item.get("font_size") or 0) < 24:
                    return {"passed": False, "reason": "font_too_small"}
                return {
                    "passed": True,
                    "reason": "approved_text_and_rendered_pixels_match",
                    "render_policy_version": item.get("render_policy_version"),
                }
    except OSError:
        return {"passed": False, "reason": "image_unreadable"}
    return {"passed": False, "reason": "hash_mismatch"}


def _read_expected_regions(
    image_path: str,
    scene: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """합성 좌표만 잘라 PSM 6으로 읽어 장면 선화의 OCR 오인식을 줄인다."""
    regions: list[tuple[int, int, int, int]] = []
    rendered = scene.get("deterministic_text_regions")
    if isinstance(rendered, list):
        for item in rendered:
            bbox = item.get("bbox") if isinstance(item, dict) else None
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                regions.append(tuple(int(value) for value in bbox))

    with Image.open(image_path) as source:
        width, height = source.size
        if not regions:
            overlays = scene.get("v5_verified_overlays")
            if isinstance(overlays, list):
                for overlay in overlays:
                    anchor = overlay.get("anchor") if isinstance(overlay, dict) else None
                    if not isinstance(anchor, dict):
                        continue
                    regions.append((
                        round(float(anchor["x"]) * width),
                        round(float(anchor["y"]) * height),
                        round((float(anchor["x"]) + float(anchor["width"])) * width),
                        round((float(anchor["y"]) + float(anchor["height"])) * height),
                    ))
        if not regions:
            return _read_tesseract_rows(image_path, psm=6)

        all_rows: list[dict[str, Any]] = []
        for region in regions:
            crop = source.convert("RGB").crop(region)
            crop = ImageOps.autocontrast(crop.convert("L")).resize(
                (max(1, crop.width * 2), max(1, crop.height * 2)),
                Image.Resampling.BICUBIC,
            )
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                temp_path = handle.name
            try:
                crop.save(temp_path, "PNG")
                statuses_and_rows = [
                    _read_tesseract_rows(temp_path, psm=psm)
                    for psm in (6, 11, 13)
                ]
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            completed_rows = [rows for status, rows in statuses_and_rows if status == "completed"]
            if not completed_rows:
                return statuses_and_rows[0][0], []
            for rows in completed_rows:
                all_rows.extend(rows)
        return "completed", all_rows


def require_final_frame_text_integrity(
    image_path: str,
    scene: dict[str, Any],
    *,
    ocr_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = inspect_final_frame_text_integrity(image_path, scene, ocr_rows=ocr_rows)
    if not report["passed"]:
        raise FinalFrameTextIntegrityError(
            "최종 이미지의 합성 문구 OCR 대조 실패: "
            f"status={report['status']}, missing_or_altered={report['missing_or_altered']}"
        )
    return report
