"""Fal/Kling에 전달할 최종 정지 이미지의 문자·수치 안전 게이트."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable

from PIL import Image, ImageOps


FAL_MOTION_SAFETY_POLICY_VERSION = 2
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


def _meaningful_surface_sequences(rows: Iterable[dict[str, Any]]) -> list[str]:
    """표면 OCR이 한글을 글자별로 쪼갠 경우 같은 행의 연속열을 복원한다.

    전체 장면 OCR에는 적용하지 않는다. 원본 해상도의 물리 표면 후보를
    따로 판독한 행만 입력받아, 승인 문구의 접두·접미 이탈자도 엄격 문자
    게이트가 실제 문자열로 비교할 수 있게 한다.
    """
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        key = tuple(str(row.get(field) or "") for field in (
            "surface_scan", "block_num", "par_num", "line_num",
        ))
        grouped.setdefault(key, []).append(row)

    sequences: list[str] = []
    for line_rows in grouped.values():
        ordered = sorted(line_rows, key=lambda row: int(row.get("word_num") or 0))
        run: list[tuple[str, float]] = []

        def flush() -> None:
            if not run:
                return
            value = "".join(text for text, _ in run)
            confidences = [confidence for _, confidence in run]
            # 모델 생성 한글은 한 글자만 낮은 신뢰도로 흔들리는 경우가 있다.
            # 전체 평균과 적어도 한 개의 강한 글자 근거를 함께 요구해 선화
            # 노이즈를 문구로 승격하지 않는다.
            if (
                len(value) >= 3
                and sum(confidences) / len(confidences) >= 55
                and max(confidences) >= 80
            ):
                sequences.append(value)
            run.clear()

        for row in ordered:
            raw_text = re.sub(r"\s+", "", str(row.get("text") or ""))
            # 글자 외곽선이나 모니터 테두리를 쉼표·따옴표로 붙여 읽어도
            # 한글 본문 자체는 보존한다. 영문·숫자가 섞인 토큰은 임의로
            # 제거하지 않고 여기서는 연속 한글 복원 대상에서 제외한다.
            if re.search(r"[A-Za-z\d]", raw_text):
                flush()
                continue
            text = "".join(re.findall(r"[가-힣]", raw_text))
            if not text:
                flush()
                continue
            try:
                confidence = float(row.get("conf") or -1)
            except (TypeError, ValueError):
                confidence = -1
            run.append((text, confidence))
        flush()
    return list(dict.fromkeys(sequences))[:20]


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


def _compact_exact_text(value: Any) -> str:
    """정확 문구 OCR에서는 표시용 공백만 제거하고 글자는 보존한다."""
    return re.sub(r"\s+", "", str(value or ""))


def _exact_text_hits(rows: Iterable[dict[str, Any]], expected_texts: Iterable[str]) -> list[str]:
    """같은 OCR 행의 완전한 연속 토큰만 승인 문구로 인정한다.

    ``비`` + ``영업이익``처럼 이웃 글자를 잘라 부분 문자열을 승인하지 않는다.
    한글을 글자별로 분할한 Tesseract 출력은 같은 행의 연속열이면 복원한다.
    """
    expected = [str(value).strip() for value in expected_texts if str(value).strip()]
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        key = tuple(str(row.get(field) or "") for field in ("block_num", "par_num", "line_num"))
        grouped.setdefault(key, []).append(row)

    hits: list[str] = []
    for target_text in expected:
        target = _compact_exact_text(target_text)
        if not target:
            continue
        for line_rows in grouped.values():
            ordered = sorted(line_rows, key=lambda row: int(row.get("word_num") or 0))
            tokens = [_compact_exact_text(row.get("text")) for row in ordered]
            matched = False
            for start in range(len(tokens)):
                joined = ""
                for end in range(start, len(tokens)):
                    joined += tokens[end]
                    if not target.startswith(joined):
                        break
                    if joined != target:
                        continue
                    before = tokens[start - 1] if start else ""
                    after = tokens[end + 1] if end + 1 < len(tokens) else ""
                    if re.search(r"[A-Za-z가-힣\d]$", before) or re.match(r"^[A-Za-z가-힣\d]", after):
                        continue
                    matched = True
                    break
                if matched:
                    break
            if matched:
                hits.append(target_text)
                break
    return list(dict.fromkeys(hits))


def _read_tesseract_rows(
    image_path: str,
    *,
    psm: int = 11,
    languages: str = "kor+eng",
) -> tuple[str, list[dict[str, str]]]:
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
            [executable, ocr_path, "stdout", "-l", languages, "--psm", str(psm), "tsv"],
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


def _read_tesseract_region_rows(
    image_path: str,
    box: tuple[int, int, int, int],
    *,
    psm: int = 6,
) -> tuple[str, list[dict[str, str]]]:
    """복잡한 전체 장면에서 놓친 큰 라벨을 국소 타일로 다시 읽는다."""
    temp_path = ""
    try:
        with Image.open(image_path) as source:
            crop = source.crop(box)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                temp_path = handle.name
            crop.save(temp_path, "PNG", optimize=True)
        return _read_tesseract_rows(temp_path, psm=psm)
    except OSError:
        return "failed", []
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _box_iou(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    width = max(0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0, min(ay2, by2) - max(ay1, by1))
    intersection = width * height
    if not intersection:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
    return intersection / union if union else 0.0


def _read_tesseract_surface_rows(
    image_path: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """밝은 물리 화면 후보를 원본 해상도·표면 기울기로 다시 읽는다.

    scene28 전용 좌표를 사용하지 않는다. 같은 프레임에 여러 모니터·보드가
    있는 장면 전반에서 사각형 표면을 찾고, 전체 960px 축소 OCR이 잃은
    접미 이탈자까지 실제 Tesseract 행으로 복원하는 공통 보조 경로다.
    """
    try:
        import cv2
    except ImportError:
        return "unavailable", [], []
    image = cv2.imread(image_path)
    if image is None:
        return "failed", [], []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    frame_area = height * width
    candidates: list[dict[str, Any]] = []
    # 동일 표면을 여러 임계값에서 중복 판독하면 비용만 늘고 OCR 노이즈가
    # 누적된다. 실제 scene28과 합성 회귀 양쪽에서 밝은 화면 내부를 안정적으로
    # 분리한 중간 임계값 하나를 사용한다.
    for threshold in (140,):
        _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if not frame_area * 0.01 <= area <= frame_area * 0.35:
                continue
            x, y, box_width, box_height = cv2.boundingRect(contour)
            if box_width < width * 0.09 or box_height < height * 0.07:
                continue
            hull = cv2.convexHull(contour)
            perimeter = cv2.arcLength(hull, True)
            approximation = cv2.approxPolyDP(hull, 0.025 * perimeter, True)
            if len(approximation) != 4:
                continue
            points = approximation.reshape(4, 2)
            ordered = sorted(points.tolist(), key=lambda point: (point[1], point[0]))
            top = sorted(ordered[:2], key=lambda point: point[0])
            angle = math.degrees(math.atan2(top[1][1] - top[0][1], top[1][0] - top[0][0]))
            # 밝은 연결 성분 경계를 소폭 확장하되, 옆 모니터와 한 타일로
            # 합쳐질 정도로 넓히지는 않는다. 아래쪽 차트 간섭은 별도의 upper
            # 변형에서 제거한다.
            pad_x = round(box_width * 0.08)
            pad_y = round(box_height * 0.08)
            box = (
                max(0, x - pad_x), max(0, y - pad_y),
                min(width, x + box_width + pad_x), min(height, y + box_height + pad_y),
            )
            candidate = {
                "box": box,
                # Tesseract 한글은 14~15도 보정에서 획을 합치는 경우가 있어
                # 과도한 기울기 추정을 13도로 제한한다. 더 큰 왜곡은 임의
                # 추정하지 않고 멀티모달/육안 게이트로 남긴다.
                "angle": max(-13.0, min(13.0, angle)),
                "area_ratio": round(area / frame_area, 6),
            }
            if any(_box_iou(box, other["box"]) >= 0.65 for other in candidates):
                continue
            candidates.append(candidate)
    candidates.sort(key=lambda item: item["area_ratio"], reverse=True)
    candidates = candidates[:8]
    if not candidates:
        return "completed", [], []

    all_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    statuses: list[str] = []
    with Image.open(image_path) as source:
        grayscale = source.convert("L")
        for candidate_index, candidate in enumerate(candidates):
            left, top, right, bottom = candidate["box"]
            box_height = bottom - top
            box_width = right - left
            scan_variants = (
                ("upper", (left, top, right, top + round(box_height * 0.72))),
                # 화면 프레임·하단 그래프를 덜어낸 내부 상단. scene28 원본의
                # 기울어진 라벨과 합성 다중 모니터 회귀가 모두 이 상대 좌표로
                # 복원되며, 절대 scene 좌표는 사용하지 않는다.
                ("interior_upper", (
                    left + round(box_width * 0.04),
                    top + round(box_height * 0.05),
                    min(width, right + round(box_width * 0.15)),
                    top + round(box_height * 0.68),
                )),
                # 글자 획이 밝은 연결 성분의 오른쪽 경계를 끊은 경우를 위해
                # 같은 표면의 오른쪽만 제한적으로 확장한다. 장면 좌표가 아닌
                # 검출된 표면 크기에 비례하므로 특정 scene 패치가 아니다.
                ("upper_right_extended", (
                    left,
                    top,
                    min(width, right + round(box_width * 0.24)),
                    top + round(box_height * 0.72),
                )),
                # 굵은 테두리·그림자까지 함께 확대하면 한글 획이 프레임과
                # 합쳐지는 표지판이 있다. 같은 검출 표면의 안쪽 12%만 잘라
                # 단일 행 PSM 7로도 읽을 수 있게 하되, 절대 장면 좌표는 쓰지 않는다.
                ("tight_interior", (
                    left + round(box_width * 0.12),
                    top + round(box_height * 0.10),
                    right - round(box_width * 0.12),
                    bottom - round(box_height * 0.10),
                )),
            )
            for variant, scan_box in scan_variants:
                crop = grayscale.crop(scan_box)
                prepared = crop.rotate(
                    candidate["angle"], expand=True, fillcolor=255,
                ).resize(
                    (crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS,
                )
                prepared = ImageOps.autocontrast(prepared)
                temp_path = ""
                try:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                        temp_path = handle.name
                    prepared.save(temp_path, "PNG", optimize=True)
                    scan_rows: list[dict[str, Any]] = []
                    for psm in (6, 7, 11):
                        status, rows = _read_tesseract_rows(
                            temp_path, psm=psm, languages="kor",
                        )
                        statuses.append(status)
                        for row in rows:
                            copied = dict(row)
                            copied["surface_scan"] = f"{candidate_index}:{variant}:{psm}"
                            scan_rows.append(copied)
                    all_rows.extend(scan_rows)
                    tokens = list(dict.fromkeys([
                        *_meaningful_ocr_tokens(scan_rows),
                        *_meaningful_surface_sequences(scan_rows),
                    ]))
                    if tokens:
                        evidence.append({
                            "source": "original_surface_deskew_ocr",
                            "candidate_index": candidate_index,
                            "variant": variant,
                            "box": list(scan_box),
                            "angle_degrees": round(candidate["angle"], 3),
                            "texts": tokens,
                        })
                finally:
                    if temp_path:
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            pass
    status = "completed" if any(value == "completed" for value in statuses) else (
        "unavailable" if statuses and all(value == "unavailable" for value in statuses) else "failed"
    )
    return status, all_rows, evidence


def _targeted_exact_text_retry(
    image_path: str,
    expected_texts: Iterable[str],
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """국소 타일에서 누락 승인 문구만 PSM 6으로 재검증한다.

    이미지 생성 모델이 쓴 짧은 승인 문구에만 사용하는 선택 경로다. 일반
    장면의 OCR 정책이나 결정론 렌더 경로를 전역적으로 바꾸지 않는다. 기본
    2열×3행이 놓친 문구만 더 작은 원본 해상도 4열×4행 타일로 한 번 더
    확인하며, 탐색 결과는 정확한 승인 문자열에만 연결한다.
    """
    remaining = [str(value).strip() for value in expected_texts if str(value).strip()]
    if not remaining:
        return "not_required", [], []
    try:
        with Image.open(image_path) as source:
            width, height = source.size
    except OSError:
        return "failed", [], []

    evidence: list[dict[str, Any]] = []
    found: list[str] = []
    statuses: list[str] = []
    scan_boxes: list[tuple[str, tuple[int, int, int, int]]] = []
    for row_index in range(3):
        for column_index in range(2):
            # 먼저 겹침 없는 큰 타일로 배경 복잡도를 줄인다.
            scan_boxes.append(("local_tile_psm6", (
                round(column_index * width / 2),
                round(row_index * height / 3),
                round((column_index + 1) * width / 2),
                round((row_index + 1) * height / 3),
            )))
    # scene47처럼 문구가 큰 타일 경계에 걸치면 배경이 다시 합쳐져
    # 사라진다. 너비를 1/4로 줄이고 세로 시작점을 1/4 간격으로
    # 옮긴 원본 타일을 보조 경로로 사용한다.
    fine_width = max(1, round(width / 4))
    fine_height = max(1, round(height / 3))
    for row_index in range(4):
        for column_index in range(4):
            left = round(column_index * width / 4)
            top = round(row_index * height / 4)
            scan_boxes.append(("local_overlap_4x4_psm6", (
                left,
                top,
                min(width, left + fine_width),
                min(height, top + fine_height),
            )))

    seen_boxes: set[tuple[int, int, int, int]] = set()
    for source, box in scan_boxes:
        if box in seen_boxes:
            continue
        seen_boxes.add(box)
        status, rows = _read_tesseract_region_rows(image_path, box, psm=6)
        statuses.append(status)
        hits = _exact_text_hits(rows, remaining)
        if not hits:
            continue
        found.extend(hits)
        evidence.append({
            "source": source,
            "tile": list(box),
            "texts": hits,
        })
        remaining = [value for value in remaining if value not in hits]
        if not remaining:
            break
    status = "completed" if any(value == "completed" for value in statuses) else (
        "unavailable" if statuses and all(value == "unavailable" for value in statuses) else "failed"
    )
    return status, list(dict.fromkeys(found)), evidence


def inspect_visible_text(
    image_path: str,
    *,
    ocr_rows: Iterable[dict[str, Any]] | None = None,
    expected_texts: Iterable[str] | None = None,
    targeted_exact_retry: bool = False,
    surface_text_recall: bool = False,
) -> dict[str, Any]:
    """최종 래스터에서 모델이 만든 읽을 수 있는 문자·숫자를 검사한다.

    Fal 후보 검사와 생성 이미지 승인 검사가 같은 OCR 임계값을 사용해야 한
    단계에서 허용한 글자를 다음 단계가 다르게 해석하지 않는다.
    """
    confirmation_status = "not_required"
    confirmation_rows: list[dict[str, Any]] = []
    expected = [str(value).strip() for value in (expected_texts or []) if str(value).strip()]
    exact_evidence: list[dict[str, Any]] = []
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
    surface_status = "not_required"
    surface_evidence: list[dict[str, Any]] = []
    surface_tokens: list[str] = []
    if ocr_rows is None and surface_text_recall:
        surface_status, surface_rows, surface_evidence = _read_tesseract_surface_rows(image_path)
        if surface_status == "completed":
            surface_candidates = list(dict.fromkeys([
                *_meaningful_ocr_tokens(surface_rows),
                *_meaningful_surface_sequences(surface_rows),
            ]))
            expected_keys = [_compact_exact_text(value) for value in expected]
            surface_tokens = [
                token for token in surface_candidates
                if not expected_keys or any(
                    _compact_exact_text(token) == key
                    or _compact_exact_text(token).startswith(key)
                    or _compact_exact_text(token).endswith(key)
                    or (
                        len(_compact_exact_text(token)) >= 3
                        and _compact_exact_text(token) in key
                    )
                    for key in expected_keys if key
                )
            ]
            tokens = list(dict.fromkeys([
                *tokens,
                *surface_tokens,
            ]))[:40]
            rows = [*rows, *surface_rows]
    surface_occurrence_counts: dict[str, int] = {}
    for value in expected:
        key = _compact_exact_text(value)
        candidate_ids = {
            int(item["candidate_index"])
            for item in surface_evidence
            if item.get("candidate_index") is not None
            and any(_compact_exact_text(text) == key for text in item.get("texts") or [])
        }
        if candidate_ids:
            surface_occurrence_counts[value] = len(candidate_ids)
    exact_texts = _exact_text_hits(rows, expected) if status == "completed" else []
    # 표면 재판독의 한 행이 승인 문자열과 완전히 같다면 주변 테두리를 별도
    # 토큰으로 읽었더라도 정확 문구로 인정한다. 접미 이탈자 `대형주수`는
    # compact equality가 아니므로 이 경로를 절대 통과하지 않는다.
    exact_texts = list(dict.fromkeys([
        *exact_texts,
        *[
            value for value in expected
            if any(_compact_exact_text(token) == _compact_exact_text(value) for token in surface_tokens)
        ],
    ]))
    if exact_texts:
        exact_evidence.append({
            "source": "provided_rows" if ocr_rows is not None else "full_frame_psm11",
            "texts": exact_texts,
        })
    missing_exact = [value for value in expected if value not in exact_texts]
    full_psm6_status = "not_required"
    if ocr_rows is None and missing_exact:
        if confirmation_status == "completed":
            full_psm6_status = "reused_numeric_confirmation"
        else:
            full_psm6_status, confirmation_rows = _read_tesseract_rows(image_path, psm=6)
        if full_psm6_status in {"completed", "reused_numeric_confirmation"}:
            full_psm6_hits = _exact_text_hits(confirmation_rows, missing_exact)
            if full_psm6_hits:
                exact_texts = list(dict.fromkeys([*exact_texts, *full_psm6_hits]))
                exact_evidence.append({"source": "full_frame_psm6", "texts": full_psm6_hits})
                missing_exact = [value for value in expected if value not in exact_texts]
    targeted_status = "not_required"
    if ocr_rows is None and targeted_exact_retry and missing_exact:
        targeted_status, targeted_hits, targeted_evidence = _targeted_exact_text_retry(
            image_path, missing_exact,
        )
        exact_texts = list(dict.fromkeys([*exact_texts, *targeted_hits]))
        exact_evidence.extend(targeted_evidence)
        missing_exact = [value for value in expected if value not in exact_texts]
    return {
        "status": status,
        "visible_tokens": tokens,
        "numeric_confirmation_status": confirmation_status,
        "exact_generated_texts": exact_texts,
        "missing_generated_texts": missing_exact,
        "targeted_exact_ocr_status": targeted_status,
        "full_frame_psm6_status": full_psm6_status,
        "exact_text_evidence": exact_evidence,
        "surface_text_ocr_status": surface_status,
        "surface_text_evidence": surface_evidence,
        "surface_occurrence_counts": surface_occurrence_counts,
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
