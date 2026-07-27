"""Marker-guided planar surface detection with conservative ambiguity handling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np

from .contracts import SurfaceContract
from .contracts import INFO_SURFACE_DETECTOR_VERSION


DETECTOR_VERSION = INFO_SURFACE_DETECTOR_VERSION

# 절대 색 일치에서 물리적 경계 대비로 바뀌면서, 기존 0.70은 정상적인
# 금속 테두리도 버리는 과도한 절단점이 됐다. 0.65는 여전히 ΔE 26 이상을
# 요구하며, 후보 간 위치·면적 경쟁은 그대로 유지한다.
PALETTE_COLLISION_MIN_BORDER_CONTRAST = .65
MIN_PLANAR_QUAD_FILL_RATIO = .78


@dataclass
class QuadDetection:
    quad: np.ndarray  # clockwise float32 (4, 2)
    surface_mask: np.ndarray
    occluder_mask: np.ndarray
    confidence: float
    color_purity: float
    border_match: float
    position_score: float
    area_ratio: float
    palette_collision: bool = False

    def as_dict(self) -> dict:
        return {
            "quad": [[round(float(x), 2), round(float(y), 2)] for x, y in self.quad],
            "confidence": round(self.confidence, 4), "color_purity": round(self.color_purity, 4),
            "border_match": round(self.border_match, 4), "position_score": round(self.position_score, 4),
            "area_ratio": round(self.area_ratio, 4), "palette_collision": self.palette_collision,
        }


def _lab_distance(image_lab: np.ndarray, rgb: tuple[int, int, int]) -> np.ndarray:
    sample = np.uint8([[[rgb[2], rgb[1], rgb[0]]]])
    target = cv2.cvtColor(sample, cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]
    # OpenCV Lab is a scaled Lab space. The threshold is a stable local
    # perceptual distance for one generated illustration, not an RGB range.
    return np.linalg.norm(image_lab.astype(np.float32) - target, axis=2)


def _order_quad(points: np.ndarray) -> np.ndarray:
    points = points.astype(np.float32)
    total = points.sum(axis=1); diff = np.diff(points, axis=1).ravel()
    return np.array([points[np.argmin(total)], points[np.argmin(diff)], points[np.argmax(total)], points[np.argmax(diff)]], dtype=np.float32)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1]); x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = max(1, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union


def _preferred_bbox(contract: SurfaceContract, width: int, height: int) -> tuple[int, int, int, int]:
    region = contract.preferred_region
    return (round(region.get("x", 0) * width), round(region.get("y", 0) * height), round((region.get("x", 0) + region.get("width", 1)) * width), round((region.get("y", 0) + region.get("height", 1)) * height))


def _keep_components(mask: np.ndarray, minimum_area: float) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    kept = np.zeros_like(mask, dtype=np.uint8)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= minimum_area:
            kept[labels == index] = 255
    return kept


def _mean_lab(lab: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    pixels = lab[mask]
    return pixels.astype(np.float32).mean(axis=0) if pixels.size else None


def _border_contrast_score(lab: np.ndarray, surface: np.ndarray, contract: SurfaceContract) -> float:
    """테두리의 절대 색이 아닌 내부·장면과의 대비 강도를 평가한다."""
    inner = cv2.erode(surface, np.ones((7, 7), np.uint8)) > 0
    # 테두리 바로 바깥 3~8px: 후보 프레임 자체의 색을 표본화한다.
    outer8 = cv2.dilate(surface, np.ones((17, 17), np.uint8)) > 0
    outer3 = cv2.dilate(surface, np.ones((7, 7), np.uint8)) > 0
    ring = outer8 & ~outer3
    # 장면 전역색은 후보와 가까운 테두리만 제외한 나머지로 계산한다.
    scene = ~(cv2.dilate(surface, np.ones((81, 81), np.uint8)) > 0)
    ring_mean, inner_mean, scene_mean = _mean_lab(lab, ring), _mean_lab(lab, inner), _mean_lab(lab, scene)
    if ring_mean is None or inner_mean is None or scene_mean is None:
        return 0.0
    contrast = min(float(np.linalg.norm(ring_mean - inner_mean)), float(np.linalg.norm(ring_mean - scene_mean)))
    score = min(1.0, contrast / 40.0)
    # 계약 색은 힌트일 뿐이다. 일치하면 +0.15 보너스를 주되 불일치로 감점하지 않는다.
    if contract.border_rgb:
        target = _lab_distance(np.uint8([[ring_mean]]), contract.border_rgb)[0, 0]
        if target <= contract.border_delta_e_max:
            score = min(1.0, score + .15)
    return score


def detect_surface_quad(image_bgr: np.ndarray, contract: SurfaceContract) -> QuadDetection | None:
    """계약된 표면색 후보 중 가장 신뢰도 높은 단일 평면을 선택한다."""
    marker_candidates = [contract.marker_rgb, *contract.marker_rgb_candidates]
    detections: list[QuadDetection] = []
    for marker in dict.fromkeys(marker_candidates):
        if marker is None:
            continue
        candidate_contract = contract.model_copy(update={"marker_rgb": marker, "marker_rgb_candidates": []})
        detection = _detect_surface_quad_for_marker(image_bgr, candidate_contract)
        if detection is not None:
            detections.append(detection)
    return max(detections, default=None, key=lambda item: item.confidence)


def _detect_surface_quad_for_marker(image_bgr: np.ndarray, contract: SurfaceContract) -> QuadDetection | None:
    if contract.geometry != "planar_quad" or contract.marker_rgb is None:
        return None
    height, width = image_bgr.shape[:2]
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    distance = _lab_distance(lab, contract.marker_rgb)
    raw = (distance <= contract.marker_delta_e_max).astype(np.uint8) * 255
    # A hanging chain or pointer may split a single paper marker into two
    # contours.  Close only the *candidate* mask with a chain-width kernel;
    # occlusion is still calculated later from the untouched colour distance.
    cleaned = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    preferred = _preferred_bbox(contract, width, height)
    candidates: list[tuple[float, QuadDetection]] = []
    for contour in contours:
        area = cv2.contourArea(contour); area_ratio = area / float(width * height)
        if not contract.area_ratio_min <= area_ratio <= contract.area_ratio_max:
            continue
        x, y, w, h = cv2.boundingRect(contour); bbox = (x, y, x + w, y + h)
        position = _iou(bbox, preferred)
        if position < contract.candidate_iou_min:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, .02 * perimeter, True)
        if len(approx) == 4:
            quad = _order_quad(approx.reshape(4, 2))
        else:
            rect = cv2.minAreaRect(contour); rect_area = max(1.0, rect[1][0] * rect[1][1])
            # 생성 장면의 실물 보드는 둥근 모서리를 자주 가진다. 0.78 미만은
            # 여전히 비사각형 장식·구름을 배제하되, 정상적인 둥근 프레임은 보존한다.
            if area / rect_area < MIN_PLANAR_QUAD_FILL_RATIO:
                continue
            quad = _order_quad(cv2.boxPoints(rect))
        surface = np.zeros((height, width), dtype=np.uint8); cv2.fillConvexPoly(surface, quad.astype(np.int32), 255)
        inside = distance[surface > 0]
        purity = float(np.mean(inside <= contract.marker_delta_e_max)) if inside.size else 0.0
        border_match = _border_contrast_score(lab, surface, contract)
        # A close surrounding dominant color makes the candidate ambiguous.
        outer = cv2.dilate(surface, np.ones((41, 41), np.uint8))
        ring = (outer > 0) & (surface == 0)
        scene_distance = distance[ring]
        palette_collision = bool(scene_distance.size and np.percentile(scene_distance, 35) < 20)
        area_target = (contract.area_ratio_min + contract.area_ratio_max) / 2
        area_score = max(0.0, 1.0 - abs(area_ratio - area_target) / max(area_target, .01))
        if palette_collision:
            score = .25 * purity + .35 * border_match + .25 * position + .15 * area_score
            if border_match < PALETTE_COLLISION_MIN_BORDER_CONTRAST:
                continue
        else:
            score = .40 * purity + .20 * border_match + .25 * position + .15 * area_score
        # The anti-aliased marker edge is not an occluder.  Remove the two
        # pixels *inside this candidate's boundary* (not merely the canvas
        # edge) before texture/noise cleanup.
        interior = cv2.erode(surface, np.ones((5, 5), np.uint8))
        raw_occluder = ((interior > 0) & (distance > contract.marker_delta_e_max)).astype(np.uint8) * 255
        opened = cv2.morphologyEx(raw_occluder, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        occluder = _keep_components(opened, .005 * area)
        candidates.append((score, QuadDetection(quad, surface, occluder, score, purity, border_match, position, area_ratio, palette_collision)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .08:
        return None
    return candidates[0][1] if candidates[0][0] >= .55 else None
