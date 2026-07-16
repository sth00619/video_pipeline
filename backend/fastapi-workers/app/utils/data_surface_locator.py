"""Find the blank in-world surface reserved for a factual data graphic.

Generated illustrations are intentionally not treated as a fixed canvas.  The
detector finds the largest warm paper/light board within the requested anchor
region, then returns an inset safe rectangle in the *actual* image geometry.
If a model changes the board position or size, the overlay follows it.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def _anchor_crop(width: int, height: int, anchor: str) -> tuple[int, int, int, int]:
    """Keep the detector away from sky/skin/mascot colours on the left."""
    if anchor.startswith("left_"):
        return 0, 0, int(width * .65), int(height * .92)
    if anchor.startswith("center_"):
        return int(width * .15), int(height * .03), int(width * .85), int(height * .92)
    return int(width * .35), int(height * .03), width, int(height * .92)


def _largest_component(mask: np.ndarray) -> tuple[int, int, int, int, int] | None:
    """Connected components without adding an OpenCV dependency to workers."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: tuple[int, int, int, int, int] | None = None
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            queue = deque([(x, y)])
            seen[y, x] = True
            area = 0
            min_x = max_x = x
            min_y = max_y = y
            while queue:
                cx, cy = queue.popleft()
                area += 1
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((nx, ny))
            candidate = (min_x, min_y, max_x + 1, max_y + 1, area)
            if best is None or candidate[4] > best[4]:
                best = candidate
    return best


def locate_data_surface(image_path: str, surface: dict[str, Any] | None = None) -> dict[str, int] | None:
    """Return a detected, inset rectangle in source-image pixels.

    The caller can safely fall back to the authored anchor when this returns
    ``None``; detection never blocks assembly.
    """
    source = Path(str(image_path or ""))
    if not source.exists():
        return None
    try:
        rgb = np.asarray(Image.open(source).convert("RGB"))
        height, width = rgb.shape[:2]
        anchor = str((surface or {}).get("anchor") or "right_panel")
        left, top, right, bottom = _anchor_crop(width, height, anchor)
        crop = rgb[top:bottom, left:right]
        # Work at a bounded size.  Paper and blank monitor interiors are warm,
        # bright, and low-saturation; printed outlines stay outside the mask.
        scale = min(1.0, 480 / max(crop.shape[0], crop.shape[1]))
        small = np.asarray(Image.fromarray(crop).resize(
            (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
            Image.Resampling.BILINEAR,
        ))
        r, g, b = (small[:, :, channel].astype(np.int16) for channel in range(3))
        mask = (
            (r >= 155) & (g >= 125) & (b >= 75)
            & (r - b >= 22) & (r - g <= 85) & (g - b <= 105)
        )
        found = _largest_component(mask)
        if not found:
            return None
        x1, y1, x2, y2, area = found
        if area < mask.size * .045:
            return None
        # Convert from detector coordinates and leave a consistent internal
        # margin so no value collides with the illustrated frame or bolts.
        sx = crop.shape[1] / mask.shape[1]
        sy = crop.shape[0] / mask.shape[0]
        x = left + int(x1 * sx)
        y = top + int(y1 * sy)
        w = int((x2 - x1) * sx)
        h = int((y2 - y1) * sy)
        inset = max(18, round(min(w, h) * .075))
        if w <= inset * 2 or h <= inset * 2:
            return None
        return {"x": x + inset, "y": y + inset, "width": w - inset * 2, "height": h - inset * 2}
    except (OSError, ValueError, KeyError):
        return None
