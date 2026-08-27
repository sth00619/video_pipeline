"""문자 표면 bbox를 원본 픽셀의 기하·선화·OCR와 연결한다."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from app.services.overlay.surface_detector import SurfaceDetection, _surface_is_text_free, detect_surface_local
from app.services.surface_text_manifest import normalized_bbox

ATTESTATION_VERSION = 1
MIN_FRAME_EDGE_DENSITY = .03
SUPPORTED_SURFACE_KINDS = {"device_screen", "signboard", "clock_display", "prop_panel", "board"}


def _interior_visual_stddev(image: Image.Image, bbox: list[int]) -> list[float]:
    """테두리를 제외한 내부 색 분산을 측정해 큰 가림 물체를 검출한다."""
    left, top, right, bottom = bbox
    inset_x = max(4, round((right - left) * .08))
    inset_y = max(4, round((bottom - top) * .08))
    interior = image.crop((left + inset_x, top + inset_y, right - inset_x, bottom - inset_y))
    if interior.width < 32 or interior.height < 24:
        raise ValueError("물리 표면 내부가 너무 작아 가림 여부를 검증할 수 없습니다.")
    return [round(float(value), 4) for value in ImageStat.Stat(interior).stddev]


def _frame_edge_density(image_path: Path, bbox: list[int]) -> float:
    """단순 색상 카드가 아니라 실제 프레임 선이 bbox 고리에 있는지 측정한다."""
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise ValueError("물리 표면 프레임 검증에 OpenCV가 필요합니다.") from exc
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("물리 표면 원본 이미지를 OpenCV로 읽을 수 없습니다.")
    height, width = image.shape[:2]
    left, top, right, bottom = bbox
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (left, top), (right, bottom), 255, thickness=-1)
    erosion = max(5, round(min(right - left, bottom - top) * .075))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erosion * 2 + 1, erosion * 2 + 1))
    inner = cv2.erode(mask, kernel)
    border = cv2.subtract(mask, inner)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)
    return round(float(np.mean(edges[border > 0] > 0)), 6)


def attest_axis_aligned_surface(image_path: str, binding: dict[str, Any]) -> dict[str, Any]:
    """축 정렬 bbox가 테두리 있는 빈 물리 표면인지 실제 픽셀로 재검증한다.

    `validated=True` 같은 입력 플래그는 증거로 사용하지 않는다. 기존 결정론
    detector의 기하·테두리·내부 선화 밀도·실제 OCR 검사를 모두 통과해야 한다.
    """
    if not isinstance(binding, dict):
        raise ValueError("물리 표면 연결은 객체여야 합니다.")
    if binding.get("geometry") != "axis_aligned_rect":
        raise ValueError("원근 표면은 좌표 변환 렌더러가 검증되기 전까지 사용할 수 없습니다.")
    kind = str(binding.get("surface_kind") or "").strip()
    if kind not in SUPPORTED_SURFACE_KINDS:
        raise ValueError("물리 표면 종류가 없거나 지원되지 않습니다.")
    path = Path(image_path)
    try:
        source = path.read_bytes()
        with Image.open(path) as image:
            size = image.size
            rgb = image.convert("RGB")
    except OSError as exc:
        raise ValueError("물리 표면 원본 이미지를 읽을 수 없습니다.") from exc
    source_sha = hashlib.sha256(source).hexdigest()
    if binding.get("image_sha256") != source_sha:
        raise ValueError("물리 표면 연결의 원본 이미지 해시가 일치하지 않습니다.")
    bbox = [float(value) for value in binding.get("bbox", [])]
    left, top, right, bottom = normalized_bbox(bbox, size)
    x, y, width, height = bbox
    detection = SurfaceDetection(
        ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        1.0,
        "heuristic",
    )
    if not _surface_is_text_free(path, detection):
        raise ValueError("물리 표면이 테두리·빈 내부·무문자·무가림 검사를 통과하지 못했습니다.")
    frame_edge_density = _frame_edge_density(path, [left, top, right, bottom])
    if frame_edge_density < MIN_FRAME_EDGE_DENSITY:
        raise ValueError("물리 표면에 충분히 분명한 프레임 선이 없습니다.")
    visual_stddev = _interior_visual_stddev(rgb, [left, top, right, bottom])
    # 단색·완만한 그라디언트 표면은 허용하되, 캐릭터·손·사물처럼 넓은
    # 전경이 내부를 덮어 채널 분산이 급증한 후보는 보수적으로 거절한다.
    # 이 임계값은 의미형 표면 v1에만 적용하며 기존 일반형 검출에는 전파하지 않는다.
    if max(visual_stddev) > 60.0:
        raise ValueError("물리 표면 내부가 사물이나 캐릭터에 가려져 있습니다.")
    crop = rgb.crop((left, top, right, bottom))
    crop_payload = (
        f"{crop.width}x{crop.height}:RGB:".encode("ascii") + crop.tobytes()
    )
    return {
        "version": ATTESTATION_VERSION,
        "validation_method": "opencv_geometry_text_free_v1",
        "source_sha256": source_sha,
        "surface_crop_sha256": hashlib.sha256(crop_payload).hexdigest(),
        "surface_bbox": bbox,
        "surface_kind": kind,
        "geometry": "axis_aligned_rect",
        "interior_channel_stddev": visual_stddev,
        "max_interior_channel_stddev": 60.0,
        "frame_edge_density": frame_edge_density,
        "min_frame_edge_density": MIN_FRAME_EDGE_DENSITY,
    }


def bind_single_local_surface(image_path: str, scene: dict[str, Any]) -> None:
    """표면 하나인 새 정책에서만 로컬 검출 결과를 명시 binding으로 만든다.

    다중 표면의 순서/의미를 추측하지 않고, 외부 비전이나 과거 vision 캐시도
    사용하지 않는다. 이미 제공된 binding은 수정하지 않고 후속 검증에 맡긴다.
    """
    items = [
        item for item in [*(scene.get("screen_text_plan") or []), *(scene.get("v5_verified_overlays") or [])]
        if isinstance(item, dict) and str(item.get("surface") or "").strip()
    ]
    names = sorted({str(item["surface"]).strip() for item in items})
    if not names:
        return
    bindings = scene.get("surface_bindings")
    if bindings is not None and not isinstance(bindings, dict):
        raise ValueError("물리 표면 연결 목록은 객체여야 합니다.")
    bindings = bindings or {}
    missing = [name for name in names if name not in bindings]
    if not missing:
        return
    if len(names) != 1 or len(missing) != 1:
        raise ValueError("다중 물리 표면은 각각의 명시적 검증 좌표가 필요합니다.")
    kinds = {
        str(item.get("surface_kind") or "board").strip()
        for item in items if str(item["surface"]).strip() == names[0]
    }
    if len(kinds) != 1 or next(iter(kinds)) not in SUPPORTED_SURFACE_KINDS:
        raise ValueError("단일 물리 표면 종류가 없거나 서로 충돌합니다.")
    kind = next(iter(kinds))
    detection = detect_surface_local(image_path, kind)  # 외부 API를 사용할 수 없는 경로
    if detection is None:
        raise ValueError("로컬 픽셀에서 안전한 빈 물리 표면을 찾지 못했습니다.")
    xs = [point[0] for point in detection.quad]
    ys = [point[1] for point in detection.quad]
    left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
    tolerance = .002
    if any(
        min(abs(x - left), abs(x - right)) > tolerance
        or min(abs(y - top), abs(y - bottom)) > tolerance
        for x, y in detection.quad
    ):
        raise ValueError("원근이 있는 검출 표면은 축 정렬 렌더러에 연결할 수 없습니다.")
    # 로컬 contour는 보통 패널 프레임의 안쪽 경계선을 반환한다. 프레임
    # 자체를 attestation 고리에 포함하도록 검출 폭/높이의 2%만 확장한다.
    # 이후 실제 프레임 밀도·내부 무문자·가림 검사가 다시 실행되므로 이
    # 확장이 열린 배경을 승인하는 우회 경로가 되지는 않는다.
    frame_padding_ratio = .02
    pad_x = (right - left) * frame_padding_ratio
    pad_y = (bottom - top) * frame_padding_ratio
    left, top = max(0.0, left - pad_x), max(0.0, top - pad_y)
    right, bottom = min(1.0, right + pad_x), min(1.0, bottom + pad_y)
    source_sha = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    bindings[names[0]] = {
        "bbox": [round(left, 5), round(top, 5), round(right - left, 5), round(bottom - top, 5)],
        "geometry": "axis_aligned_rect",
        "surface_kind": kind,
        "image_sha256": source_sha,
        "detector_evidence": {
            "strategy": detection.strategy,
            "confidence": detection.confidence,
            "quad": [list(point) for point in detection.quad],
            "paid_api_calls": 0,
            "cache_policy": "local_pixels_only_no_vision_cache",
            "frame_padding_ratio": frame_padding_ratio,
        },
    }
    scene["surface_bindings"] = bindings


def attest_scene_surfaces(image_path: str, scene: dict[str, Any]) -> None:
    """실제로 사용되는 표면만 검증하고 서로 다른 표면의 중첩을 거절한다."""
    bindings = scene.get("surface_bindings")
    if not isinstance(bindings, dict):
        raise ValueError("물리 표면 연결 목록이 없습니다.")
    names = {
        str(item.get("surface") or "")
        for item in [*(scene.get("screen_text_plan") or []), *(scene.get("v5_verified_overlays") or [])]
        if isinstance(item, dict) and str(item.get("surface") or "")
    }
    if not names:
        return
    boxes: list[tuple[str, list[int]]] = []
    with Image.open(image_path) as image:
        size = image.size
    for name in sorted(names):
        binding = bindings.get(name)
        if not isinstance(binding, dict):
            raise ValueError(f"물리 표면 연결이 없습니다: {name}")
        binding["attestation"] = attest_axis_aligned_surface(image_path, binding)
        boxes.append((name, normalized_bbox(binding["bbox"], size)))
    for index, (name, box) in enumerate(boxes):
        for other_name, other in boxes[index + 1:]:
            if max(box[0], other[0]) < min(box[2], other[2]) and max(box[1], other[1]) < min(box[3], other[3]):
                raise ValueError(f"서로 다른 물리 표면이 겹칩니다: {name}, {other_name}")
