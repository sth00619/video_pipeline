"""Two-stage, fail-closed detector for blank in-world numeric surfaces.

Stage one is local OpenCV geometry.  Stage two is an explicitly enabled
Claude-vision fallback, budgeted once per data scene.  A failed detector never
guesses perspective: callers retain their authored cloud/anchor placement.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import numpy as np
from PIL import Image, ImageStat

from app.utils.budget import can_charge_overlay_vision, record_cost
from app.utils.data_surface_locator import locate_data_surface

SurfaceKind = Literal["device_screen", "signboard", "clock_display", "prop_panel", "board"]
Quad = tuple[tuple[float, float], ...]
VisionResolver = Callable[[str, SurfaceKind], tuple[Quad, float] | None]
_SURFACE_CACHE_POLICY_VERSION = 3


@dataclass(frozen=True)
class SurfaceDetection:
    quad: Quad
    confidence: float
    strategy: Literal["opencv", "heuristic", "vision"]


def _normalise_quad(points: np.ndarray, width: int, height: int) -> Quad | None:
    if points.shape != (4, 2):
        return None
    result = tuple((round(float(x) / width, 5), round(float(y) / height, 5)) for x, y in points)
    if any(x < 0 or y < 0 or x > 1 or y > 1 for x, y in result):
        return None
    area = abs(sum(result[i][0] * result[(i + 1) % 4][1] - result[(i + 1) % 4][0] * result[i][1] for i in range(4))) / 2
    # 수치 표면은 장면을 지배하는 전면 카드가 아니라 세트 안의 소품이어야 한다.
    # 프레임 20%를 넘는 후보는 캐릭터·배경까지 포함한 오검출일 가능성이 높다.
    return result if .025 <= area <= .20 else None


def _opencv_quad(path: Path) -> SurfaceDetection | None:
    """Find a large, low-texture quadrilateral without assuming its location."""
    try:
        import cv2
    except ImportError:
        return None
    image = cv2.imread(str(path))
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = min(1.0, 960 / max(width, height))
    small = cv2.resize(image, (round(width * scale), round(height * scale))) if scale < 1 else image
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best: tuple[float, np.ndarray] | None = None
    image_area = small.shape[0] * small.shape[1]
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * .035:
            continue
        approximation = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            continue
        points = approximation.reshape(4, 2).astype(float)
        x, y, w, h = cv2.boundingRect(approximation)
        if w < 80 or h < 55 or not .35 <= w / h <= 4.5:
            continue
        crop = gray[y:y + h, x:x + w]
        if crop.size == 0 or float(np.std(crop)) > 54:
            continue
        rectangularity = area / max(1, w * h)
        mean_brightness = float(np.mean(crop)) / 255.0
        center_y = (y + h / 2) / max(1, small.shape[0])
        upper_scene_bias = max(.2, 1.0 - center_y * .65)
        # 넓은 책상 전면·벽보다 실제 발광 모니터를 우선한다. 면적만 크게
        # 보상하면 화면이 비어 있어도 하단 가구에 숫자가 붙는 문제가 생긴다.
        score = (
            min(1.0, area / image_area * 4.0) * .30
            + rectangularity * .25
            + mean_brightness * .35
            + upper_scene_bias * .10
        )
        if best is None or score > best[0]:
            best = (score, points / scale)
    if not best:
        return None
    quad = _normalise_quad(best[1], width, height)
    return SurfaceDetection(quad, round(best[0], 3), "opencv") if quad else None


def _heuristic_quad(path: Path) -> SurfaceDetection | None:
    surface = locate_data_surface(str(path), {"anchor": "right_panel"})
    if not surface:
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
            crop = image.crop((surface["x"], surface["y"], surface["x"] + surface["width"], surface["y"] + surface["height"])).convert("L")
            if ImageStat.Stat(crop).stddev[0] > 34:
                return None
            x, y = surface["x"] / width, surface["y"] / height
            w, h = surface["width"] / width, surface["height"] / height
            return SurfaceDetection(((x, y), (x + w, y), (x + w, y + h), (x, y + h)), .42, "heuristic")
    except OSError:
        return None


def _sliding_blank_surface(path: Path) -> SurfaceDetection | None:
    """닫힌 외곽선 일부가 캐릭터에 가려져도 넓은 저선화 정보판 내부를 찾는다."""
    try:
        import cv2
    except ImportError:
        return None
    image = cv2.imread(str(path))
    if image is None:
        return None
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)
    best: tuple[float, tuple[float, float, float, float]] | None = None
    # 수치 표면은 한 줄의 한국어 금액을 읽을 수 있는 최소 면적이 필요하다.
    # 화면 하단은 바닥·책상 같은 저선화 영역이 많아 상단 2/3만 탐색한다.
    for region_width in (.22, .26, .30, .34):
        # 진행자가 화면 하단 일부를 가리는 정보형 구도에서는 전체 모니터를
        # 고집하면 캐릭터까지 덮게 된다. 물리 프레임의 위·좌·우 경계가 남은
        # 얕은 티커 영역도 후보로 보되, 아래의 3면 경계·OCR·최소 면적 검증은
        # 그대로 통과해야 하므로 열린 배경을 임의 표면으로 쓰지는 않는다.
        for region_height in (.11, .13, .16, .20, .24, .28):
            if region_width * region_height < .025:
                continue
            for x in np.arange(.04, .96 - region_width, .02):
                for y in np.arange(.04, .66 - region_height, .02):
                    left, right = round(x * width), round((x + region_width) * width)
                    top, bottom = round(y * height), round((y + region_height) * height)
                    crop_edges = edges[top:bottom, left:right]
                    crop_gray = gray[top:bottom, left:right]
                    crop_hsv = hsv[top:bottom, left:right]
                    edge_density = float(np.mean(crop_edges > 0))
                    mean_brightness = float(np.mean(crop_gray))
                    mean_saturation = float(np.mean(crop_hsv[:, :, 1]))
                    if mean_brightness < 150 or edge_density > .045:
                        continue
                    # 넓지만 캐릭터·차트가 들어간 영역보다 조금 얕아도 실제로
                    # 비어 있는 화면 띠를 우선한다. 선화 밀도를 면적보다 강하게
                    # 벌점 처리해야 진행자 머리·손을 덮는 합성을 막을 수 있다.
                    blank_factor = max(.02, 1.0 - edge_density / .045) ** 2
                    score = (
                        region_width * region_height
                        * blank_factor
                        * (mean_brightness / 255.0)
                        * max(.20, 1.0 - min(mean_saturation, 120.0) / 180.0)
                    )
                    if best is None or score > best[0]:
                        best = (score, (float(x), float(y), region_width, region_height))
    # 얕은 티커형 화면은 면적 가중 점수가 낮다. 여기서는 후보만 넓게 받고,
    # 실제 채택은 _surface_geometry_is_safe의 최소 면적·3면 경계 검증이 맡는다.
    if best is None or best[0] < .0015:
        return None
    score, (x, y, region_width, region_height) = best
    quad: Quad = (
        (round(x, 5), round(y, 5)),
        (round(x + region_width, 5), round(y, 5)),
        (round(x + region_width, 5), round(y + region_height, 5)),
        (round(x, 5), round(y + region_height, 5)),
    )
    return SurfaceDetection(quad, round(min(.9, .60 + score * 5.0), 3), "heuristic")


def _claude_vision_quad(path: str, surface_kind: SurfaceKind) -> tuple[Quad, float] | None:
    """Ask Claude only for JSON geometry; it never supplies visible copy."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        response = anthropic.Anthropic(api_key=api_key).messages.create(
            model="claude-sonnet-4-6", max_tokens=220,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encoded}},
                {"type": "text", "text": (
                    "Locate exactly one largest blank, text-free illustrated " + surface_kind +
                    " suitable for a factual numeric overlay. Return the largest fully visible, unobstructed blank rectangle within the physical screen, board, or panel. "
                    "Never include a character, face, hand, prop, globe, chart, or open background inside the returned quad. "
                    "Reject every surface that already contains any letter, number, glyph, or label. Prefer a large bright blank screen even when one corner is partly occluded. "
                    "If a mascot covers the lower part of a screen, return only a sufficiently tall blank upper band whose top, left, and right physical frame edges remain visible; never include the covered area. "
                    "In a finance control-room illustration, first check the large illuminated wall screen on the left side; use it when its interior is blank. "
                    "When a blank screen occupies more than six percent of the frame, never return a smaller labeled sign. "
                    "Return up to four candidates sorted by usable blank area as JSON only: "
                    '{"candidates":[{"quad":[[x,y],[x,y],[x,y],[x,y]],"confidence":0-1}]}. '
                    "Coordinates must be normalized. Return an empty candidates array when uncertain."
                )},
            ]}],
        )
        text = "".join(getattr(block, "text", "") for block in response.content)
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            candidates = [data]
        parsed: list[tuple[Quad, float]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            points = np.asarray(candidate.get("quad"), dtype=float)
            quad = _normalise_quad(points, 1, 1)
            confidence = float(candidate.get("confidence", 0))
            if quad and confidence >= .6:
                parsed.append((quad, confidence))
        # 모델의 정렬을 그대로 믿지 않고 실제 면적으로 다시 정렬한다.
        parsed.sort(key=lambda item: _surface_blankness_score(Path(path), item[0]), reverse=True)
        for quad, confidence in parsed:
            detection = SurfaceDetection(quad, confidence, "vision")
            if _surface_is_text_free(Path(path), detection):
                return quad, confidence
        return None
    except (Exception,):  # Vision is optional; preserve the deterministic fallback.
        return None


def _surface_blankness_score(path: Path, quad: Quad) -> float:
    """넓이만이 아니라 내부 선화 밀도가 낮은 실제 빈 표면을 우선한다."""
    area = abs(sum(
        quad[i][0] * quad[(i + 1) % 4][1]
        - quad[(i + 1) % 4][0] * quad[i][1]
        for i in range(4)
    )) / 2
    try:
        import cv2

        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return area
        height, width = image.shape[:2]
        xs = [point[0] for point in quad]
        ys = [point[1] for point in quad]
        crop = image[
            max(0, round(min(ys) * height)):min(height, round(max(ys) * height)),
            max(0, round(min(xs) * width)):min(width, round(max(xs) * width)),
        ]
        if crop.size == 0:
            return 0.0
        edges = cv2.Canny(cv2.GaussianBlur(crop, (5, 5), 0), 35, 110)
        edge_density = float(np.mean(edges > 0))
        # 구형 지구본·차트처럼 넓지만 선화가 촘촘한 후보보다, 조금 작아도
        # 빈 모니터 내부가 우선되도록 면적에 선화 패널티를 곱한다.
        return area * max(.05, 1.0 - edge_density * 8.0)
    except (ImportError, OSError, ValueError):
        return area


def _surface_is_text_free(path: Path, detection: SurfaceDetection) -> bool:
    """검출 표면 안에 기존 문자가 있으면 새 승인 문구의 대상으로 쓰지 않는다."""
    if not _surface_geometry_is_safe(path, detection):
        return False
    try:
        from app.services.fal_motion_safety import _meaningful_ocr_tokens, _read_tesseract_rows

        with Image.open(path) as source:
            width, height = source.size
            xs = [point[0] for point in detection.quad]
            ys = [point[1] for point in detection.quad]
            left, top = round(min(xs) * width), round(min(ys) * height)
            right, bottom = round(max(xs) * width), round(max(ys) * height)
            if left >= right or top >= bottom:
                return False
            crop = source.convert("RGB").crop((left, top, right, bottom))
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                temp_path = handle.name
            crop.save(temp_path, "PNG")
        try:
            rows: list[dict] = []
            for psm in (6, 11):
                status, current = _read_tesseract_rows(temp_path, psm=psm)
                if status == "completed":
                    rows.extend(current)
            return not _meaningful_ocr_tokens(rows)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    except (OSError, ValueError):
        return False


def _surface_geometry_is_safe(path: Path, detection: SurfaceDetection) -> bool:
    """실제 테두리 안의 저선화 면인지 확인해 배경·캐릭터 오검출을 막는다."""
    try:
        import cv2

        image = cv2.imread(str(path))
        if image is None:
            return False
        height, width = image.shape[:2]
        points = np.asarray([
            [round(x * width), round(y * height)] for x, y in detection.quad
        ], dtype=np.int32)
        area = abs(float(cv2.contourArea(points))) / max(1.0, float(width * height))
        if not .025 <= area <= .20:
            return False

        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(mask, points, 255)
        x, y, w, h = cv2.boundingRect(points)
        if w < width * .16 or h < height * .11 or not .45 <= w / max(1, h) <= 4.5:
            return False

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)
        erosion = max(5, round(min(w, h) * .075))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erosion * 2 + 1, erosion * 2 + 1))
        inner = cv2.erode(mask, kernel)
        if int(np.count_nonzero(inner)) < 500:
            return False
        border = cv2.subtract(mask, inner)
        inner_density = float(np.mean(edges[inner > 0] > 0))
        border_density = float(np.mean(edges[border > 0] > 0)) if np.any(border > 0) else 0.0
        band = max(4, round(min(w, h) * .045))
        side_regions = (
            edges[max(0, y - band):min(height, y + band), x:min(width, x + w)],
            edges[max(0, y + h - band):min(height, y + h + band), x:min(width, x + w)],
            edges[y:min(height, y + h), max(0, x - band):min(width, x + band)],
            edges[y:min(height, y + h), max(0, x + w - band):min(width, x + w + band)],
        )
        side_densities = [
            float(np.mean(region > 0)) if region.size else 0.0
            for region in side_regions
        ]
        bounded_sides = sum(value >= .008 for value in side_densities)

        # 한글·숫자·얼굴·차트는 내부 선화 밀도를 크게 높인다. 반대로 실제 빈
        # 모니터는 내부가 단순하고 경계 고리에 프레임 선이 존재한다.
        return inner_density <= .032 and bounded_sides >= 3
    except (ImportError, OSError, ValueError):
        return False


def detect_surface(
    image_path: str,
    surface_kind: SurfaceKind,
    *,
    job_id: int | None = None,
    scene_key: str = "",
    vision_resolver: VisionResolver | None = None,
) -> SurfaceDetection | None:
    path = Path(str(image_path or ""))
    if not path.is_file():
        return None
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    cache_path = path.with_name(path.name + ".surface-detection.json")
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if (
            cached.get("policy_version") == _SURFACE_CACHE_POLICY_VERSION
            and cached.get("source_sha256") == source_hash
            and cached.get("surface_kind") == surface_kind
        ):
            detected = SurfaceDetection(
                tuple(tuple(float(value) for value in point) for point in cached["quad"]),
                float(cached["confidence"]),
                str(cached["strategy"]),
            )
            if _surface_is_text_free(path, detected):
                return detected
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass

    def remember(detected: SurfaceDetection) -> SurfaceDetection:
        payload = {
            "policy_version": _SURFACE_CACHE_POLICY_VERSION,
            "source_sha256": source_hash,
            "surface_kind": surface_kind,
            "quad": [list(point) for point in detected.quad],
            "confidence": detected.confidence,
            "strategy": detected.strategy,
        }
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=cache_path.parent, prefix=cache_path.name, delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                temp_name = handle.name
            os.replace(temp_name, cache_path)
        except OSError:
            pass
        return detected

    # 첫 번째 사각형을 곧바로 채택하면 넓은 책상 전면이 실제 밝은 모니터보다
    # 먼저 검출되는 경우가 있었다. 독립 검출기들이 찾은 안전 후보를 모두
    # 비교해 가장 높은 신뢰도의 장면 내 표면을 선택한다.
    candidates = [
        detected
        for detected in (_opencv_quad(path), _heuristic_quad(path), _sliding_blank_surface(path))
        if detected and _surface_is_text_free(path, detected)
    ]
    if candidates:
        return remember(max(candidates, key=lambda value: value.confidence))
    enabled = os.getenv("OVERLAY_VISION_ENABLED", "true").lower() in {"1", "true", "yes"}
    budget_scene_key = f"{scene_key}:{source_hash[:12]}"
    if not enabled or job_id is None or not scene_key or not can_charge_overlay_vision(job_id, budget_scene_key):
        return None
    result = (vision_resolver or _claude_vision_quad)(str(path), surface_kind)
    if not result:
        return None
    quad, confidence = result
    if confidence < .6:
        return None
    record_cost(job_id, "overlay_vision", scene_key=budget_scene_key)
    detected = SurfaceDetection(quad, round(confidence, 3), "vision")
    return remember(detected) if _surface_is_text_free(path, detected) else None


def detect_surface_local(image_path: str, surface_kind: SurfaceKind) -> SurfaceDetection | None:
    """외부 비전·과금 원장·과거 vision 캐시 없이 로컬 픽셀만 검사한다."""
    path = Path(str(image_path or ""))
    if not path.is_file():
        return None
    candidates = [
        detected
        for detected in (_opencv_quad(path), _heuristic_quad(path), _sliding_blank_surface(path))
        if detected and _surface_is_text_free(path, detected)
    ]
    return max(candidates, key=lambda value: value.confidence) if candidates else None


def detect_surface_quad(image_path: str, surface_kind: SurfaceKind) -> Quad | None:
    """Compatibility API used by existing callers."""
    detected = detect_surface(image_path, surface_kind)
    return detected.quad if detected else None
