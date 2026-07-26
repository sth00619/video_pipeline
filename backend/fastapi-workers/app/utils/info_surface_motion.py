"""QA helpers for proving an in-world surface moves with its source still."""
from __future__ import annotations

import math
from typing import Iterable


def inverse_map_point(point: tuple[float, float], transform: dict[str, float]) -> tuple[float, float]:
    """Map a screen point through a recorded scale/translation inverse."""
    scale = float(transform.get("scale", 1.0))
    if scale <= 0:
        raise ValueError("scale must be positive")
    return ((point[0] - float(transform.get("tx", 0))) / scale, (point[1] - float(transform.get("ty", 0))) / scale)


def max_inverse_anchor_delta(samples: Iterable[tuple[tuple[float, float], dict[str, float]]]) -> float:
    mapped = [inverse_map_point(point, transform) for point, transform in samples]
    if len(mapped) < 2:
        return 0.0
    base = mapped[0]
    return max(math.dist(base, point) for point in mapped[1:])


def max_inverse_relative_anchor_delta(
    samples: Iterable[tuple[tuple[float, float], tuple[float, float], dict[str, float]]],
) -> float:
    """Measure text-to-surface drift in original image coordinates.

    Each sample contains the screen-space text anchor, a screen-space surface
    anchor, and the recorded affine crop/scale transform for that frame.  A
    normal Ken Burns transform changes absolute screen positions; the inverse
    relative vector must remain stable when both are baked into one PNG.
    """
    vectors = []
    for text_anchor, surface_anchor, transform in samples:
        text = inverse_map_point(text_anchor, transform)
        surface = inverse_map_point(surface_anchor, transform)
        vectors.append((text[0] - surface[0], text[1] - surface[1]))
    if len(vectors) < 2:
        return 0.0
    base = vectors[0]
    return max(math.dist(base, vector) for vector in vectors[1:])


def max_normalized_anchor_delta(samples: Iterable[tuple[tuple[float, float], tuple[float, float], float]]) -> float:
    values = [math.dist(text, surface) / max(1.0, diagonal) for text, surface, diagonal in samples]
    return max(values) - min(values) if values else 0.0
