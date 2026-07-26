"""Two-stage, fail-closed detector for blank in-world numeric surfaces.

Stage one is local OpenCV geometry.  Stage two is an explicitly enabled
Claude-vision fallback, budgeted once per data scene.  A failed detector never
guesses perspective: callers retain their authored cloud/anchor placement.
"""
from __future__ import annotations

import base64
import json
import os
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
    return result if .025 <= area <= .72 else None


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
        score = min(1.0, area / image_area * 3.0) * .55 + rectangularity * .45
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


def _claude_vision_quad(path: str, surface_kind: SurfaceKind) -> tuple[Quad, float] | None:
    """Ask Claude only for JSON geometry; it never supplies visible copy."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        response = anthropic.Anthropic(api_key=api_key).messages.create(
            model=os.getenv("OVERLAY_VISION_MODEL", "claude-sonnet-4-6"), max_tokens=220,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encoded}},
                {"type": "text", "text": (
                    "Locate exactly one blank, text-free illustrated " + surface_kind +
                    " suitable for a factual numeric overlay. Return JSON only: "
                    '{"quad":[[x,y],[x,y],[x,y],[x,y]],"confidence":0-1}. '
                    "Coordinates must be normalized. Return null when uncertain."
                )},
            ]}],
        )
        text = "".join(getattr(block, "text", "") for block in response.content)
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        points = np.asarray(data.get("quad"), dtype=float)
        quad = _normalise_quad(points, 1, 1)
        confidence = float(data.get("confidence", 0))
        return (quad, confidence) if quad and confidence >= .6 else None
    except (Exception,):  # Vision is optional; preserve the deterministic fallback.
        return None


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
    detected = _opencv_quad(path) or _heuristic_quad(path)
    if detected:
        return detected
    enabled = os.getenv("OVERLAY_VISION_ENABLED", "true").lower() in {"1", "true", "yes"}
    if not enabled or job_id is None or not scene_key or not can_charge_overlay_vision(job_id, scene_key):
        return None
    result = (vision_resolver or _claude_vision_quad)(str(path), surface_kind)
    if not result:
        return None
    quad, confidence = result
    if confidence < .6:
        return None
    record_cost(job_id, "overlay_vision", scene_key=scene_key)
    return SurfaceDetection(quad, round(confidence, 3), "vision")


def detect_surface_quad(image_path: str, surface_kind: SurfaceKind) -> Quad | None:
    """Compatibility API used by existing callers."""
    detected = detect_surface(image_path, surface_kind)
    return detected.quad if detected else None
