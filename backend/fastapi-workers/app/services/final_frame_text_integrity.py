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
from app.services.surface_text_manifest import expected_cells, validate_manifest


class FinalFrameTextIntegrityError(RuntimeError):
    """최종 프레임의 문구가 예정 문구와 일치하지 않을 때 발생한다."""


def _normalise(value: Any) -> str:
    # 오탈자·숫자 변형을 숨기지 않는다. OCR 줄바꿈과 공백만 제거한다.
    return re.sub(r"\s+", "", str(value or "")).strip()


def expected_final_frame_texts(scene: dict[str, Any]) -> list[str]:
    """결정론 렌더러가 이 장면에 실제로 써야 하는 문자열을 반환한다."""
    if scene.get("surface_text_manifest") or scene.get("text_render_policy") == "semantic_roles_v1":
        return list(expected_cells(scene).values())
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
    # 반복 문구도 실제 출력 횟수만큼 대조한다. 중복 제거는 누락을 숨긴다.
    return expected


def inspect_final_frame_text_integrity(
    image_path: str,
    scene: dict[str, Any],
    *,
    ocr_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """예정 문구가 최종 래스터에서 글자·숫자 그대로 읽히는지 검사한다."""
    try:
        expected = expected_final_frame_texts(scene)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"status": "invalid_surface_contract", "passed": False,
                "expected": [], "recognized": [], "missing_or_altered": []}
    if not expected:
        return {
            "status": "not_applicable",
            "passed": True,
            "expected": [],
            "recognized": [],
            "missing_or_altered": [],
        }

    if ocr_rows is None:
        status, regions = _read_expected_regions(image_path, scene)
    else:
        if scene.get("surface_text_manifest") or scene.get("text_render_policy") == "semantic_roles_v1":
            return {"status": "spatial_ocr_required", "passed": False, "expected": expected,
                    "recognized": [], "missing_or_altered": expected}
        # 주입 행은 한 번의 관측이다. 실제 OCR/좌표 검증을 했다는 뜻은 아니다.
        status, regions = "completed", [{
            "region_index": 0, "expected": expected,
            "attempts": [{"psm": None, "status": "completed", "rows": list(ocr_rows)}],
        }]
    if status != "completed":
        return {
            "status": status,
            "passed": False,
            "expected": expected,
            "recognized": [],
            "missing_or_altered": expected,
        }

    comparisons = []
    recognized = []
    missing = []
    for region in regions:
        attempts = []
        target = _normalise("\n".join(region["expected"]))
        for attempt in region["attempts"]:
            texts = [str(row.get("text") or "").strip() for row in attempt["rows"]
                     if str(row.get("text") or "").strip()]
            recognized.extend(texts)
            attempts.append({
                "psm": attempt["psm"], "status": attempt["status"],
                "recognized": texts,
                "exact_match": attempt["status"] == "completed"
                and _normalise("\n".join(texts)) == target,
            })
        # 서로 다른 재독 결과의 일부를 이어 붙이거나, 불일치 관측을 버리고
        # 일치한 관측만 고르지 않는다. 애매한 판독은 검토 대상으로 남긴다.
        region_passed = bool(attempts) and all(item["exact_match"] for item in attempts)
        comparisons.append({
            "region_index": region["region_index"], "expected": region["expected"],
            "cell_id": region.get("cell_id"), "bbox": region.get("bbox"),
            "passed": region_passed, "attempts": attempts,
        })
        if not region_passed:
            missing.extend(region["expected"])
    ocr_passed = bool(comparisons) and all(item["passed"] for item in comparisons)
    provenance = _inspect_deterministic_render_provenance(image_path, scene, expected)
    # Tesseract는 정자형 한글도 `억/열`처럼 오판할 수 있다. 승인 문자열과
    # 렌더 직후 픽셀 영역 해시가 모두 일치할 때만 OCR 오판을 보완한다.
    # 생성 모델이 직접 쓴 문구에는 이 예외가 적용되지 않는다.
    passed = ocr_passed or bool(provenance.get("passed"))
    return {
        "status": status,
        "passed": passed,
        "ocr_passed": ocr_passed,
        "verification_method": "ocr_exact" if ocr_passed else (
            "deterministic_pixel_provenance" if passed else "none"
        ),
        "comparison_policy": "ordered_exact_whitespace_only_all_attempts_v1",
        "ocr_source": "injected_rows" if ocr_rows is not None else "tesseract",
        "region_comparisons": comparisons,
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
    if scene.get("surface_text_manifest") or scene.get("text_render_policy") == "semantic_roles_v1":
        return {"passed": False, "reason": "cellwise_exact_ocr_required"}
    if not isinstance(rendered, list) or not rendered:
        return {"passed": False, "reason": "metadata_missing"}
    # 현재 렌더러는 전체 캡션을 한 영역에 기록한다. 여러 영역 중 하나의
    # 해시만 맞는 것으로 다른 표면의 잘못된 값까지 승인하지 않는다.
    if len(rendered) != 1 or scene.get("v5_verified_overlays"):
        return {"passed": False, "reason": "unsupported_provenance_scope"}
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
                left, top, right, bottom = (int(value) for value in bbox)
                if not (0 <= left < right <= rgb.width and 0 <= top < bottom <= rgb.height):
                    continue
                crop = rgb.crop((left, top, right, bottom))
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
    except (TypeError, ValueError, OverflowError):
        return {"passed": False, "reason": "invalid_metadata"}
    return {"passed": False, "reason": "hash_mismatch"}


def _read_expected_regions(
    image_path: str,
    scene: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """표면별 예정 문자열과 PSM 6/11/13 관측을 분리해 보존한다."""
    expected = expected_final_frame_texts(scene)
    regions = []
    rendered = scene.get("deterministic_text_regions")
    try:
        source = Image.open(image_path)
    except OSError:
        return "image_unreadable", []
    with source:
        width, height = source.size
        overlays = scene.get("v5_verified_overlays")
        try:
            if scene.get("surface_text_manifest") or scene.get("text_render_policy") == "semantic_roles_v1":
                cells = validate_manifest(scene, source.size)
                regions = [(tuple(cell["bbox"]), [cell["text"]], cell["psm_modes"], cell["id"]) for cell in cells]
            elif isinstance(overlays, list) and overlays:
                for overlay in overlays:
                    if not isinstance(overlay, dict):
                        return "invalid_surface_contract", []
                    # 추세선의 시작/종료값은 별도 위치 계약이 필요하다. 라벨과
                    # 값만 검사하고 나머지 수치를 승인했다고 보고하지 않는다.
                    if overlay.get("visualization", "text") != "text":
                        return "unsupported_surface_layout", []
                    anchor = overlay["anchor"]
                    bbox = (
                        round(float(anchor["x"]) * width),
                        round(float(anchor["y"]) * height),
                        round((float(anchor["x"]) + float(anchor["width"])) * width),
                        round((float(anchor["y"]) + float(anchor["height"])) * height),
                    )
                    texts = [str(overlay.get(key) or "").strip() for key in ("label", "value")]
                    if not all(texts):
                        return "invalid_surface_contract", []
                    regions.append((bbox, texts, [6, 11, 13], None))
            elif rendered:
                if not isinstance(rendered, list) or len(rendered) != 1:
                    return "ambiguous_surface_contract", []
                regions.append((tuple(int(value) for value in rendered[0]["bbox"]), expected, [6, 11, 13], None))
        except (KeyError, TypeError, ValueError, OverflowError):
            return "invalid_surface_contract", []
        for bbox, _, _, _ in regions:
            if len(bbox) != 4 or not (0 <= bbox[0] < bbox[2] <= width
                                     and 0 <= bbox[1] < bbox[3] <= height):
                return "invalid_surface_contract", []
        if not regions:
            status, rows = _read_tesseract_rows(image_path, psm=6)
            return status, [{"region_index": 0, "expected": expected,
                             "attempts": [{"psm": 6, "status": status, "rows": rows}]}]

        observations: list[dict[str, Any]] = []
        for index, (bbox, texts, modes, cell_id) in enumerate(regions):
            crop = source.convert("RGB").crop(bbox)
            crop = ImageOps.autocontrast(crop.convert("L")).resize(
                (max(1, crop.width * 2), max(1, crop.height * 2)),
                Image.Resampling.BICUBIC,
            )
            if cell_id is not None:
                # 실제 잉크 bbox만 자르면 판독기가 글자 가장자리를 놓친다.
                # 인접 표면의 문자를 섞지 않고, 새 빈 여백만 추가한다.
                corners = sorted(crop.getpixel(point) for point in (
                    (0, 0), (crop.width - 1, 0), (0, crop.height - 1), (crop.width - 1, crop.height - 1),
                ))
                if (corners[1] + corners[2]) / 2 < 128:
                    crop = ImageOps.invert(crop)
                # 큰 단일 문자를 다시 두 배 확대하면 줄/글자 분할이 불안정하다.
                # 판독 사본만 행당 64px로 맞추며 원본 프레임과 승인 문구는 유지한다.
                target_height = 64 * max(1, texts[0].count("\n") + 1)
                crop = crop.resize((max(1, round(crop.width * target_height / crop.height)), target_height),
                                   Image.Resampling.LANCZOS)
                crop = ImageOps.expand(crop, border=24, fill=255)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                temp_path = handle.name
            try:
                crop.save(temp_path, "PNG")
                attempts = []
                for psm in modes:
                    status, rows = _read_tesseract_rows(temp_path, psm=psm)
                    attempts.append({"psm": psm, "status": status, "rows": rows})
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            observations.append({"region_index": index, "expected": texts, "attempts": attempts,
                                 "cell_id": cell_id, "bbox": list(bbox)})
        return "completed", observations


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
